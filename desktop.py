"""Standalone Qt desktop host. Python and Qt are bundled by PyInstaller."""
import os
import sys
import time
import threading
import traceback
import socket
import multiprocessing
from pathlib import Path

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
os.environ['DO_NOT_TRACK'] = '1'
os.environ['HF_HUB_DISABLE_PROGRESS_BARS'] = '1'
os.environ['OMP_NUM_THREADS'] = '4'

def main():
    from app.storage import ROOT, RESOURCE_ROOT, DATA
    if getattr(sys, 'frozen', False):
        # Windowed executables have no console for logging frameworks to write to.
        output = (DATA / 'desktop.log').open('w', encoding='utf-8', buffering=1)
        sys.stdout = output
        sys.stderr = output

    from PySide6.QtCore import QTimer, QUrl, Qt, QStandardPaths
    from PySide6.QtGui import QIcon
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QFileDialog
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineUrlRequestInterceptor, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView

    app = QApplication(sys.argv)
    app.setApplicationName('Nipahut AI Transcriber')
    app.setOrganizationName('NipahutAITranscriber')
    app.setWindowIcon(QIcon(str(RESOURCE_ROOT / 'static' / 'app.ico')))

    # Launching the EXE again brings the existing desktop window forward.
    instance = QLocalSocket()
    instance.connectToServer('NipahutAITranscriberDesktop-8765')
    if instance.waitForConnected(300):
        instance.write(b'activate')
        instance.flush()
        instance.waitForBytesWritten(300)
        return 0
    single_instance = QLocalServer()
    QLocalServer.removeServer('NipahutAITranscriberDesktop-8765')
    if not single_instance.listen('NipahutAITranscriberDesktop-8765'):
        QMessageBox.critical(None, 'Nipahut AI Transcriber', 'Another instance is starting. Please try again.')
        return 1

    try:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 8765))
    except OSError:
        QMessageBox.warning(None, 'Nipahut AI Transcriber',
            'Port 8765 is in use by another instance of the audio engine. Close the previous app or development server, then open Nipahut AI Transcriber again.')
        return 1

    class LocalRequestsOnly(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self, info):
            url = info.requestUrl()
            permitted = (url.scheme() in ('about', 'data', 'blob') or
                         (url.scheme() == 'http' and url.host() == '127.0.0.1' and url.port() == 8765))
            if not permitted:
                info.block(True)

    class LocalPage(QWebEnginePage):
        def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
            return (url.scheme() in ('about', 'data', 'blob') or
                    (url.scheme() == 'http' and url.host() == '127.0.0.1' and url.port() == 8765))

    server_box = {'server': None, 'error': None}
    def engine():
        try:
            import uvicorn
            from app.server import app as api_app
            server = uvicorn.Server(uvicorn.Config(api_app, host='127.0.0.1', port=8765,
                log_level='warning', access_log=False, loop='asyncio', http='h11', ws='none'))
            server_box['server'] = server
            server.run()
        except BaseException as error:
            server_box['error'] = str(error)
            traceback.print_exc()

    class AudioWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle('Nipahut AI Transcriber')
            screen = app.primaryScreen().availableGeometry()
            self.resize(min(1480, screen.width() - 50), min(940, screen.height() - 50))
            self.setMinimumSize(900, 650)
            self.allow_close = False
            self.closing = False
            # Off-the-record rendering avoids browser-profile/cache folders.
            # App preferences and recordings persist in our own local data folder.
            self.profile = QWebEngineProfile(self)
            self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.NoCache)
            self.interceptor = LocalRequestsOnly(self.profile)
            self.profile.setUrlRequestInterceptor(self.interceptor)
            self.profile.downloadRequested.connect(self.save_download)
            self.view = QWebEngineView(self)
            self.page = LocalPage(self.profile, self.view)
            self.view.setPage(self.page)
            self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
            self.page.settings().setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
            self.setCentralWidget(self.view)
            self.view.setHtml('<html><body style="background:#f5f7f8;color:#182333;font-family:Segoe UI;text-align:center;padding-top:20vh"><h1>Nipahut AI Transcriber</h1><p>Starting the local audio engine…</p></body></html>')
            self.statusBar().showMessage('Starting local audio engine…')
            self.started = time.monotonic()
            self.timer = QTimer(self)
            self.timer.timeout.connect(self.check_ready)
            self.timer.start(150)

        def check_ready(self):
            server = server_box['server']
            if server and server.started:
                self.timer.stop()
                self.view.load(QUrl('http://127.0.0.1:8765/'))
                self.statusBar().showMessage('Local desktop app · files stay on this computer')
            elif server_box['error'] or time.monotonic() - self.started > 45:
                self.timer.stop()
                QMessageBox.critical(self, 'Nipahut AI Transcriber could not start',
                    server_box['error'] or 'Startup timed out. See data/desktop.log for details.')
                self.allow_close = True
                self.close()

        def save_download(self, request):
            name = Path(request.downloadFileName() or 'transcript.txt').name
            directory = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
            target, _ = QFileDialog.getSaveFileName(self, 'Export transcript', str(Path(directory) / name), 'Transcript files (*.pdf *.txt *.srt *.json *.rttm);;All files (*)')
            if target:
                target_path = Path(target)
                request.setDownloadDirectory(str(target_path.parent))
                request.setDownloadFileName(target_path.name)
                request.accept()
                self.statusBar().showMessage('Exporting to ' + str(target_path), 8000)
            else:
                request.cancel()

        def closeEvent(self, event):
            if self.allow_close:
                event.accept()
                return
            from app.pipeline import work
            if work.snapshot()['state'] == 'running':
                if not self.closing:
                    answer = QMessageBox.question(self, 'Processing in progress',
                        'Cancel processing and close Nipahut AI Transcriber? The original audio and saved results will be retained.',
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No)
                    if answer != QMessageBox.StandardButton.Yes:
                        event.ignore()
                        return
                    self.closing = True
                    work.cancel()
                    self.view.setEnabled(False)
                    self.statusBar().showMessage('Closing after the current audio block finishes…')
                event.ignore()
                QTimer.singleShot(250, self.close)
                return
            self.allow_close = True
            event.accept()

    window = AudioWindow()
    def activate():
        connection = single_instance.nextPendingConnection()
        if connection:
            connection.readAll()
            connection.disconnectFromServer()
        window.showNormal()
        window.raise_()
        window.activateWindow()
    single_instance.newConnection.connect(activate)
    worker = threading.Thread(target=engine, name='local-audio-engine', daemon=True)
    worker.start()
    window.show()
    exit_code = app.exec()
    server = server_box['server']
    if server:
        server.should_exit = True
        worker.join(10)
    single_instance.close()
    return exit_code

if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise
