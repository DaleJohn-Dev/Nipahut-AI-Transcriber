from app import server,pipeline
from fastapi import HTTPException
import pytest

def test_roster_of_24_includes_interviewers_and_additional_people():
 roster,total=server.ParticipantSetup(interviewers=['Fictional Ana','Fictional Ben','Fictional Clara','Fictional Dan'],additional_speakers=20).checked()
 assert total==24 and roster['additional_speakers']==20
 assert server.Preferences(speaker_count=24).speaker_count==24

@pytest.mark.parametrize('args',[
 {'interviewers':['Ana'],'participants':['ana']},
 {'interviewers':['']},
 {'interviewers':['A','B'],'additional_speakers':31},
])
def test_roster_rejects_duplicates_blank_names_and_capacity_overflow(args):
 with pytest.raises(HTTPException):server.ParticipantSetup(**args).checked()

def test_roster_names_are_not_assigned_to_voices_by_list_order():
 proposals={'speaker_08':{'name':'Ana','evidence':'My name is Ana.'}}
 result=pipeline.roster_name_hints(proposals,{'interviewers':['Ben Smith','Ana Cruz']})
 assert result['speaker_08']['name']=='Ana Cruz'
 assert list(result)==['speaker_08']
 assert pipeline.roster_name_hints({}, {'interviewers':['Ana Cruz']})=={}
