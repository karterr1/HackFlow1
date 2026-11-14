import io, os
from datetime import timedelta
import pytest
from app import create_app,db,seed_data,User,Hack,Task,Submission,Member,now
@pytest.fixture()
def app():
    app=create_app({'TESTING':True,'SQLALCHEMY_DATABASE_URI':os.environ.get('TEST_DATABASE_URL','sqlite://'),'SECRET_KEY':'test-only'})
    with app.app_context():db.create_all();seed_data()
    yield app
    with app.app_context():db.session.remove();db.drop_all()
def token(c):return c.get('/api/csrf').json['token']
def post(c,path,data):return c.post('/api'+path,json=data,headers={'X-CSRFToken':token(c)})
def patch(c,path,data):return c.patch('/api'+path,json=data,headers={'X-CSRFToken':token(c)})
def signin(c,name):return post(c,'/login',{'email':name+'@hackflow.local','password':'HackFlow2026!'})
def test_complete_official_scenario(app):
    captain=app.test_client();member=app.test_client();org=app.test_client()
    assert signin(member,'member').status_code==200
    assert post(member,'/hacks/1/join',{'code':'HACKFLOW-DEMO'}).status_code==200
    assert post(member,'/hacks/1/teams',{'name':'Вторая команда'}).status_code==409
    assert len(member.get('/api/teams/1').json['members'])==2
    s=member.get('/api/hacks/1/space').json
    assert s['cases'] and s['resources']
    resource=next(x for x in s['resources'] if x['kind']=='material')
    assert post(member,f"/resources/{resource['id']}/complete",{}).status_code==200
    t=post(member,'/teams/1/tasks',{'title':'Интеграционный тест'}).json
    assert patch(member,f"/tasks/{t['id']}",{'status':'done','assignee':2}).status_code==200
    assert post(member,'/teams/1/messages',{'text':'Всё готово!'}).json[-1]['text']=='Всё готово!'
    payload={'title':'HackFlow','description':'Рабочее решение','github':'https://github.com/example/hackflow','demo':'https://example.com','presentation':'https://example.com/slides.pdf'}
    assert post(member,'/teams/1/submit',payload).status_code==403
    signin(captain,'captain')
    assert post(captain,'/teams/1/submit',payload).status_code==201
    assert post(captain,'/teams/1/submit',payload).status_code==409
    signin(org,'organizer')
    result=org.get('/api/hacks/1/manage').json
    assert result['teams'][0]['submission']['title']=='HackFlow'
    assert result['teams'][0]['tasks']
def test_closed_access_and_idor(app):
    c=app.test_client()
    assert post(c,'/register',{'email':'outsider@example.com','nick':'Чужой','password':'LongPassword2026!'}).status_code==201
    for path in ['/hacks/1/space','/teams/1','/teams/1/messages','/hacks/1/manage','/admin/users']:
        assert c.get('/api'+path).status_code==403
    assert post(c,'/hacks/1/join',{'code':'HACKFLOW-DEMO'}).status_code==403
    assert patch(c,'/tasks/1',{'status':'done'}).status_code==403
    assert post(c,'/resources/1/complete',{}).status_code==403
    assert not c.get('/api/hacks').json[0]['admitted']
def test_csrf_and_limits(app):
    c=app.test_client()
    assert c.post('/api/login',json={}).status_code==400
    assert post(c,'/register',{'email':'bad','nick':'x','password':'short'}).status_code==400
    signin(c,'captain')
    assert patch(c,'/tasks/1',{'status':'invalid'}).status_code==400
    assert patch(c,'/tasks/1',{'assignee':999}).status_code==400
    assert c.delete('/api/teams/1',headers={'X-CSRFToken':token(c)}).status_code==409
    with app.app_context():h=db.session.get(Hack,1);h.deadline=now()-timedelta(days=1);db.session.commit()
    assert post(c,'/teams/1/submit',{}).status_code==409
def test_organizer_import_publish_edit(app):
    c=app.test_client();signin(c,'organizer')
    r=c.post('/api/hacks/1/admissions',data={'file':(io.BytesIO(b'email\nnew@example.com\n'),'allowed.csv')},headers={'X-CSRFToken':token(c)})
    assert r.status_code==200
    assert post(c,'/hacks/1/resources',{'kind':'event','title':'Вебинар','url':'javascript:alert(1)'}).status_code==400
    r=post(c,'/hacks/1/resources',{'kind':'event','title':'Вебинар','url':'https://telemost.yandex.ru','date':'2027-01-01T12:00:00Z'})
    assert r.status_code==201
    rid=r.json['id']
    assert patch(c,f'/resources/{rid}',{'title':'Обновлённый вебинар'}).status_code==200
    assert c.delete(f'/api/resources/{rid}',headers={'X-CSRFToken':token(c)}).status_code==200
    assert c.get('/api/teams/1/messages').status_code==403

def test_team_privacy(app):
    a=app.test_client();b=app.test_client();signin(a,'captain');signin(b,'member')
    other=post(b,'/hacks/1/teams',{'name':'Другая команда'}).json
    assert a.get(f"/api/teams/{other['id']}").status_code==403
    assert a.get(f"/api/teams/{other['id']}/messages").status_code==403
    assert post(a,f"/teams/{other['id']}/tasks",{'title':'Атака'}).status_code==403

def test_registered_user_gets_access_after_organizer_admission(app):
    newcomer=app.test_client();org=app.test_client()
    assert post(newcomer,'/register',{'email':'new@example.com','nick':'Новый участник','password':'HackFlow2026!'}).status_code==201
    assert newcomer.get('/api/me').status_code==200
    assert not newcomer.get('/api/hacks').json[0]['admitted']
    assert newcomer.get('/api/hacks/1/space').status_code==403
    signin(org,'organizer')
    assert post(org,'/hacks/1/admissions',{'email':'new@example.com'}).status_code==200
    assert newcomer.get('/api/hacks').json[0]['admitted']
    assert newcomer.get('/api/notices').json[0]['text'].startswith('Вы допущены')
    assert post(newcomer,'/hacks/1/join',{'code':'HACKFLOW-DEMO'}).status_code==200
    assert post(newcomer,'/teams/1/tasks',{'title':'Задача нового участника'}).status_code==201
    assert post(newcomer,'/teams/1/messages',{'text':'Теперь всё доступно'}).json[-1]['text']=='Теперь всё доступно'

def test_invalid_csrf_has_machine_readable_error(app):
    c=app.test_client();signin(c,'captain')
    r=c.post('/api/teams/1/tasks',json={'title':'Не создавать'},headers={'X-CSRFToken':'expired'})
    assert r.status_code==400 and r.json['code']=='csrf_failed'
    with app.app_context():assert Task.query.filter_by(title='Не создавать').count()==0
    assert post(c,'/teams/1/tasks',{'title':'Повтор с новым токеном'}).status_code==201

def test_progress_is_scoped_to_hack_and_learning_material(app):
    c=app.test_client();org=app.test_client();signin(c,'captain');signin(org,'organizer')
    assert post(c,'/resources/1/complete',{}).status_code==200
    assert post(c,'/resources/3/complete',{}).status_code==400
    h=post(org,'/hacks',{'name':'Другой хакатон','start':'2026-01-01T00:00:00','deadline':'2027-01-01T00:00:00'}).json
    post(org,f"/hacks/{h['id']}/admissions",{'email':'captain@hackflow.local'})
    assert c.get(f"/api/hacks/{h['id']}/space").json['completed']==[]
    assert c.get('/api/hacks/1/space').json['completed']==[1]

def test_task_can_clear_optional_description_and_deadline(app):
    c=app.test_client();signin(c,'captain')
    r=patch(c,'/tasks/1',{'title':'Новое название','description':'','deadline':None})
    assert r.status_code==200 and r.json['description']=='' and r.json['deadline'] is None

def test_local_secret_survives_restart(tmp_path):
    import importlib.util
    from pathlib import Path
    spec=importlib.util.spec_from_file_location('run_local',Path(__file__).parents[1]/'run_local.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    one=module.persistent_secret(tmp_path/'instance')
    assert len(one)>=64 and module.persistent_secret(tmp_path/'instance')==one

def test_seed_can_add_demo_after_registration_without_erasing_user(app):
    with app.app_context():db.drop_all();db.create_all()
    c=app.test_client()
    assert post(c,'/register',{'email':'real@example.com','nick':'Александр','password':'OwnPassword2026!'}).status_code==201
    with app.app_context():
        seed_data();seed_data()
        assert User.query.filter_by(email='real@example.com').one().nick=='Александр'
        assert User.query.count()==5
        assert Hack.query.count()==1
        assert User.query.filter_by(email='organizer@hackflow.local').one().role=='organizer'
    org=app.test_client();assert signin(org,'organizer').status_code==200
