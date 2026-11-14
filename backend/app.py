import os, secrets, csv, io
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
from flask import Flask, Blueprint, request, jsonify, abort, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import HTTPException
from sqlalchemy.exc import IntegrityError

db=SQLAlchemy(); login=LoginManager(); csrf=CSRFProtect()
def now(): return datetime.now(timezone.utc).replace(tzinfo=None)
class User(UserMixin, db.Model):
    id=db.Column(db.Integer,primary_key=True)
    email=db.Column(db.String(200),unique=True,nullable=False)
    nick=db.Column(db.String(80),unique=True,nullable=False)
    password=db.Column(db.String(255),nullable=False)
    role=db.Column(db.String(30),default='participant',nullable=False)
    blocked=db.Column(db.Boolean,default=False)
class Hack(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    name=db.Column(db.String(200),nullable=False)
    description=db.Column(db.Text,default='')
    start=db.Column(db.DateTime,nullable=False)
    deadline=db.Column(db.DateTime,nullable=False)
    owner=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    capacity=db.Column(db.Integer,default=5)
class Admission(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    hack_id=db.Column(db.Integer,db.ForeignKey('hack.id'),nullable=False)
    email=db.Column(db.String(200),nullable=False)
    __table_args__=(db.UniqueConstraint('hack_id','email'),)
class Team(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    hack_id=db.Column(db.Integer,db.ForeignKey('hack.id'),nullable=False)
    name=db.Column(db.String(120),nullable=False)
    captain=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    code=db.Column(db.String(40),unique=True,default=lambda:secrets.token_urlsafe(12))
    case_id=db.Column(db.Integer,db.ForeignKey('case.id'))
class Member(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    hack_id=db.Column(db.Integer,db.ForeignKey('hack.id'),nullable=False)
    team_id=db.Column(db.Integer,db.ForeignKey('team.id'),nullable=False)
    __table_args__=(db.UniqueConstraint('user_id','hack_id'),)
class Case(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    hack_id=db.Column(db.Integer,db.ForeignKey('hack.id'),nullable=False)
    title=db.Column(db.String(200),nullable=False)
    body=db.Column(db.Text,nullable=False)
class Task(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    team_id=db.Column(db.Integer,db.ForeignKey('team.id'),nullable=False)
    title=db.Column(db.String(200),nullable=False)
    description=db.Column(db.Text,default='')
    assignee=db.Column(db.Integer,db.ForeignKey('user.id'))
    status=db.Column(db.String(20),default='todo',nullable=False)
    deadline=db.Column(db.DateTime)
    created=db.Column(db.DateTime,default=now)
    __table_args__=(db.CheckConstraint("status IN ('todo','doing','review','done')"),)
class Message(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    team_id=db.Column(db.Integer,db.ForeignKey('team.id'),nullable=False)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    text=db.Column(db.Text,nullable=False)
    created=db.Column(db.DateTime,default=now)
class Resource(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    hack_id=db.Column(db.Integer,db.ForeignKey('hack.id'),nullable=False)
    kind=db.Column(db.String(20),nullable=False)
    title=db.Column(db.String(200),nullable=False)
    body=db.Column(db.Text,default='')
    url=db.Column(db.Text,default='')
    date=db.Column(db.DateTime)
class Progress(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    resource_id=db.Column(db.Integer,db.ForeignKey('resource.id'),nullable=False)
    __table_args__=(db.UniqueConstraint('user_id','resource_id'),)
class Submission(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    team_id=db.Column(db.Integer,db.ForeignKey('team.id'),unique=True,nullable=False)
    title=db.Column(db.String(200),nullable=False)
    description=db.Column(db.Text,nullable=False)
    github=db.Column(db.Text,nullable=False)
    demo=db.Column(db.Text,nullable=False)
    presentation=db.Column(db.Text,nullable=False)
    created=db.Column(db.DateTime,default=now)
class Notice(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    text=db.Column(db.Text,nullable=False)
    read=db.Column(db.Boolean,default=False)
    created=db.Column(db.DateTime,default=now)
class Audit(db.Model):
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=False)
    action=db.Column(db.Text,nullable=False)
    created=db.Column(db.DateTime,default=now)

def dump(obj, fields=None):
    fields=fields or [c.name for c in obj.__table__.columns]
    return {k:(getattr(obj,k).isoformat()+'Z' if isinstance(getattr(obj,k),datetime) else getattr(obj,k)) for k in fields}
def data(): return request.get_json(silent=True) or {}
def text(d,key,limit=200):
    v=d.get(key,'')
    if not isinstance(v,str) or not v.strip() or len(v.strip())>limit: abort(400,description=f'Проверьте поле {key}')
    return v.strip()
def url(d,key):
    v=text(d,key,2000); p=urlsplit(v)
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password: abort(400,description='Нужна ссылка http/https')
    return v

def create_app(config=None):
    app=Flask(__name__,static_folder='../frontend/dist',static_url_path='/assets-static')
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL','sqlite:///hackflow.db'),MAX_CONTENT_LENGTH=2*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','0')=='1',WTF_CSRF_TIME_LIMIT=3600)
    if config: app.config.update(config)
    db.init_app(app); login.init_app(app); csrf.init_app(app); Migrate(app,db)
    CORS(app,origins=[os.environ.get('FRONTEND_ORIGIN','http://localhost:5173')],supports_credentials=True)
    limiter=Limiter(get_remote_address,app=app,storage_uri=os.environ.get('RATELIMIT_STORAGE_URI','memory://'))
    @login.user_loader
    def load(uid):
        u=db.session.get(User,int(uid)); return u if u and not u.blocked else None
    @login.unauthorized_handler
    def unauthorized(): return jsonify(error='Войдите в аккаунт'),401
    @app.errorhandler(HTTPException)
    def error(e): return jsonify(error=e.description),e.code
    @app.errorhandler(IntegrityError)
    def conflict(e): db.session.rollback(); return jsonify(error='Запись уже существует или нарушено ограничение'),409
    api=Blueprint('api',__name__,url_prefix='/api')
    def owner(h):
        if current_user.role!='admin' and h.owner!=current_user.id: abort(403)
    def access(h):
        if current_user.role=='admin' or h.owner==current_user.id:return
        if not Admission.query.filter_by(hack_id=h.id,email=current_user.email).first():abort(403,description='Нет допуска к этому хакатону')
    def gethack(hid):
        h=db.get_or_404(Hack,hid); access(h); return h
    def getteam(tid,manage=False):
        t=db.get_or_404(Team,tid); h=gethack(t.hack_id)
        if manage and (current_user.role=='admin' or h.owner==current_user.id):return t
        if not Member.query.filter_by(team_id=t.id,user_id=current_user.id).first():abort(403)
        return t
    def notify(hid,msg):
        emails=[x.email for x in Admission.query.filter_by(hack_id=hid)]
        for u in User.query.filter(User.email.in_(emails)): db.session.add(Notice(user_id=u.id,text=msg))
    @api.get('/csrf')
    def token():return jsonify(token=generate_csrf())
    @api.post('/register')
    @limiter.limit('10/hour')
    def register():
        d=data(); email=text(d,'email').lower(); nick=text(d,'nick',80); pw=text(d,'password',128)
        if '@' not in email or len(pw)<10:abort(400,description='Проверьте email; пароль — минимум 10 символов')
        u=User(email=email,nick=nick,password=generate_password_hash(pw));db.session.add(u);db.session.commit();login_user(u);return jsonify(dump(u,['id','email','nick','role'])),201
    @api.post('/login')
    @limiter.limit('10/minute')
    def signin():
        d=data();u=User.query.filter_by(email=text(d,'email').lower()).first()
        if not u or u.blocked or not check_password_hash(u.password,d.get('password','')):abort(401,description='Неверный email или пароль')
        login_user(u);return jsonify(dump(u,['id','email','nick','role']))
    @api.post('/logout')
    @login_required
    def signout():logout_user();return jsonify(ok=True)
    @api.get('/me')
    @login_required
    def me():return jsonify(dump(current_user,['id','email','nick','role']))
    @api.get('/hacks')
    @login_required
    def hacks():return jsonify([dict(dump(h),admitted=current_user.role=='admin' or h.owner==current_user.id or bool(Admission.query.filter_by(hack_id=h.id,email=current_user.email).first())) for h in Hack.query.all()])
    @api.get('/hacks/<int:hid>/space')
    @login_required
    def space(hid):
        h=gethack(hid);m=Member.query.filter_by(hack_id=hid,user_id=current_user.id).first()
        return jsonify(hack=dump(h),cases=[dump(c) for c in Case.query.filter_by(hack_id=hid)],teams=[dump(t,['id','name','captain','case_id']) for t in Team.query.filter_by(hack_id=hid)],team_id=m.team_id if m else None,resources=[dump(r) for r in Resource.query.filter_by(hack_id=hid)],completed=[p.resource_id for p in Progress.query.filter_by(user_id=current_user.id)],manager=current_user.role=='admin' or h.owner==current_user.id)
    @api.post('/hacks')
    @login_required
    def create_hack():
        if current_user.role not in ('admin','organizer'):abort(403)
        d=data()
        try:start=datetime.fromisoformat(d['start']).replace(tzinfo=None);end=datetime.fromisoformat(d['deadline']).replace(tzinfo=None)
        except (KeyError,ValueError,TypeError):abort(400)
        if end<=start:abort(400)
        h=Hack(name=text(d,'name'),description=d.get('description',''),start=start,deadline=end,owner=current_user.id);db.session.add(h);db.session.commit();return jsonify(dump(h)),201
    @api.post('/hacks/<int:hid>/cases')
    @login_required
    def create_case(hid):
        h=db.get_or_404(Hack,hid);owner(h);d=data()
        c=Case(hack_id=hid,title=text(d,'title'),body=text(d,'body',10000))
        db.session.add(c);notify(hid,'Опубликован новый кейс');db.session.commit();return jsonify(dump(c)),201
    @api.post('/hacks/<int:hid>/teams')
    @login_required
    def team_create(hid):
        gethack(hid);t=Team(hack_id=hid,name=text(data(),'name',120),captain=current_user.id);db.session.add(t);db.session.flush();db.session.add(Member(user_id=current_user.id,hack_id=hid,team_id=t.id));db.session.commit();return jsonify(dump(t)),201
    @api.post('/hacks/<int:hid>/join')
    @login_required
    def join(hid):
        h=gethack(hid);t=Team.query.filter_by(hack_id=hid,code=text(data(),'code')).first_or_404()
        db.session.execute(db.select(Team).where(Team.id==t.id).with_for_update()).scalar_one()
        if Member.query.filter_by(team_id=t.id).count()>=h.capacity:abort(409,description='В команде нет мест')
        db.session.add(Member(user_id=current_user.id,hack_id=hid,team_id=t.id));db.session.commit();return jsonify(ok=True)
    @api.route('/teams/<int:tid>',methods=['GET','PATCH','DELETE'])
    @login_required
    def team(tid):
        t=getteam(tid,manage=True)
        if request.method=='GET':return jsonify(team=dump(t),members=[dump(db.session.get(User,m.user_id),['id','nick']) for m in Member.query.filter_by(team_id=tid)],tasks=[dump(x) for x in Task.query.filter_by(team_id=tid)],submission=dump(s) if (s:=Submission.query.filter_by(team_id=tid).first()) else None)
        if current_user.id!=t.captain:owner(db.session.get(Hack,t.hack_id))
        if request.method=='DELETE':
            if now()>=db.session.get(Hack,t.hack_id).start:abort(409,description='После старта удаление запрещено')
            if Submission.query.filter_by(team_id=tid).first():abort(409)
            for model in (Task,Message,Member):model.query.filter_by(team_id=tid).delete()
            db.session.delete(t)
        else:
            c=db.get_or_404(Case,data().get('case_id'))
            if c.hack_id!=t.hack_id:abort(400)
            t.case_id=c.id
        db.session.commit();return jsonify(ok=True)
    @api.post('/teams/<int:tid>/tasks')
    @login_required
    def task_create(tid):
        getteam(tid); d=data();t=Task(team_id=tid,title=text(d,'title'),description=d.get('description',''));db.session.add(t);db.session.commit();return jsonify(dump(t)),201
    @api.patch('/tasks/<int:tid>')
    @login_required
    def task_edit(tid):
        t=db.get_or_404(Task,tid);getteam(t.team_id);d=data()
        if 'status' in d:
            if d['status'] not in ('todo','doing','review','done'):abort(400)
            t.status=d['status']
        if 'title' in d:t.title=text(d,'title')
        if 'description' in d:t.description=text(d,'description',5000)
        if 'assignee' in d:
            if d['assignee'] is not None and not Member.query.filter_by(team_id=t.team_id,user_id=d['assignee']).first():abort(400)
            t.assignee=d['assignee']
        if 'deadline' in d:
            try:t.deadline=datetime.fromisoformat(d['deadline']).replace(tzinfo=None) if d['deadline'] else None
            except (ValueError,TypeError):abort(400)
        db.session.commit();return jsonify(dump(t))
    @api.route('/teams/<int:tid>/messages',methods=['GET','POST'])
    @login_required
    def messages(tid):
        getteam(tid)
        if request.method=='POST':
            m=Message(team_id=tid,user_id=current_user.id,text=text(data(),'text',4000));db.session.add(m)
            for member in Member.query.filter_by(team_id=tid):
                if member.user_id!=current_user.id:db.session.add(Notice(user_id=member.user_id,text='Новое сообщение в командном чате'))
            db.session.commit()
        return jsonify([dict(dump(m),author=db.session.get(User,m.user_id).nick) for m in Message.query.filter_by(team_id=tid).order_by(Message.id.desc()).limit(100).all()[::-1]])
    @api.post('/resources/<int:rid>/complete')
    @login_required
    def complete(rid):
        r=db.get_or_404(Resource,rid);gethack(r.hack_id)
        p=Progress.query.filter_by(user_id=current_user.id,resource_id=rid).first()
        if p:db.session.delete(p)
        else:db.session.add(Progress(user_id=current_user.id,resource_id=rid))
        db.session.commit();return jsonify(ok=True)
    @api.post('/teams/<int:tid>/submit')
    @login_required
    def submit(tid):
        t=getteam(tid);h=db.session.get(Hack,t.hack_id)
        if t.captain!=current_user.id:abort(403,description='Отправляет капитан')
        if now()>h.deadline:abort(409,description='Дедлайн завершён')
        if not t.case_id:abort(400,description='Сначала выберите кейс')
        d=data();s=Submission(team_id=tid,title=text(d,'title'),description=text(d,'description',10000),github=url(d,'github'),demo=url(d,'demo'),presentation=url(d,'presentation'))
        if urlsplit(s.github).hostname!='github.com':abort(400,description='Укажите репозиторий github.com')
        db.session.add(s);db.session.add(Audit(user_id=current_user.id,action=f'Отправка команды {tid}'));notify(h.id,'Команда отправила итоговый проект');db.session.commit();return jsonify(dump(s)),201
    @api.get('/notices')
    @login_required
    def notices():return jsonify([dump(n) for n in Notice.query.filter_by(user_id=current_user.id).order_by(Notice.id.desc()).limit(100)])
    @api.post('/notices/read')
    @login_required
    def read_notices():Notice.query.filter_by(user_id=current_user.id).update({'read':True});db.session.commit();return jsonify(ok=True)
    @api.post('/hacks/<int:hid>/admissions')
    @login_required
    def admissions(hid):
        h=db.get_or_404(Hack,hid);owner(h)
        if request.files:
            f=request.files.get('file')
            if not f:abort(400)
            try:emails=[row['email'].strip().lower() for row in csv.DictReader(io.StringIO(f.read().decode('utf-8-sig')))]
            except (KeyError,UnicodeError):abort(400,description='CSV должен содержать колонку email')
        else:emails=[text(data(),'email').lower()]
        if any('@' not in e or len(e)>200 for e in emails):abort(400)
        for e in set(emails):
            if not Admission.query.filter_by(hack_id=hid,email=e).first():db.session.add(Admission(hack_id=hid,email=e))
        db.session.add(Audit(user_id=current_user.id,action=f'Импорт допуска: {hid}, {len(emails)}'));db.session.commit();return jsonify(ok=True,count=len(emails))
    @api.route('/hacks/<int:hid>/resources',methods=['POST'])
    @login_required
    def resources(hid):
        h=db.get_or_404(Hack,hid);owner(h);d=data();kind=d.get('kind')
        if kind not in ('material','event','announcement'):abort(400)
        date=None
        if d.get('date'):
            try:date=datetime.fromisoformat(d['date']).replace(tzinfo=None)
            except ValueError:abort(400)
        r=Resource(hack_id=hid,kind=kind,title=text(d,'title'),body=d.get('body',''),url=url(d,'url') if d.get('url') else '',date=date);db.session.add(r);notify(hid,'Опубликовано: '+r.title);db.session.commit();return jsonify(dump(r)),201
    @api.route('/resources/<int:rid>',methods=['PATCH','DELETE'])
    @login_required
    def resource_edit(rid):
        r=db.get_or_404(Resource,rid);owner(db.session.get(Hack,r.hack_id))
        if request.method=='DELETE':Progress.query.filter_by(resource_id=rid).delete();db.session.delete(r)
        else:
            d=data()
            if 'title' in d:r.title=text(d,'title')
            if 'body' in d:r.body=d['body']
            if 'url' in d:r.url=url(d,'url') if d['url'] else ''
            if 'date' in d:
                try:r.date=datetime.fromisoformat(d['date']).replace(tzinfo=None) if d['date'] else None
                except ValueError:abort(400)
        notify(r.hack_id,'Материалы или расписание изменены');db.session.commit();return jsonify(ok=True)
    @api.get('/hacks/<int:hid>/manage')
    @login_required
    def manage(hid):
        h=db.get_or_404(Hack,hid);owner(h);teams=Team.query.filter_by(hack_id=hid).all()
        return jsonify(admissions=Admission.query.filter_by(hack_id=hid).count(),teams=[dict(dump(t),members=Member.query.filter_by(team_id=t.id).count(),tasks=[dump(x) for x in Task.query.filter_by(team_id=t.id)],submission=dump(s) if (s:=Submission.query.filter_by(team_id=t.id).first()) else None) for t in teams])
    @api.route('/admin/users',methods=['GET','PATCH'])
    @login_required
    def users():
        if current_user.role!='admin':abort(403)
        if request.method=='PATCH':
            d=data();u=db.get_or_404(User,d.get('id'))
            if u.id==current_user.id:abort(400)
            if 'role' in d:
                if d['role'] not in ('participant','organizer','jury'):abort(400)
                u.role=d['role']
            if 'blocked' in d:u.blocked=bool(d['blocked'])
            db.session.add(Audit(user_id=current_user.id,action=f'Изменение пользователя {u.id}'));db.session.commit()
        return jsonify([dump(u,['id','nick','email','role','blocked']) for u in User.query.all()])
    app.register_blueprint(api)
    @app.get('/')
    @app.get('/<path:path>')
    def frontend(path='index.html'):
        if path.startswith('api/'):abort(404)
        root=os.path.abspath(app.static_folder)
        return send_from_directory(root,path if os.path.isfile(os.path.join(root,path)) else 'index.html')
    @app.cli.command('seed')
    def seed():seed_data()
    @app.cli.command('init-admin')
    def init_admin():
        import click
        email=click.prompt('Email').strip().lower();pw=click.prompt('Пароль (10+ символов)',hide_input=True,confirmation_prompt=True)
        if len(pw)<10:raise click.ClickException('Пароль слишком короткий')
        db.session.add(User(email=email,nick='Администратор',password=generate_password_hash(pw),role='admin'));db.session.commit()
    return app

def seed_data():
    if User.query.first():return
    people=[]
    for name,role in [('captain','participant'),('member','participant'),('organizer','organizer'),('jury','jury')]:
        u=User(email=f'{name}@hackflow.local',nick={'captain':'Александр','member':'Мария','organizer':'Организатор','jury':'Эксперт'}[name],role=role,password=generate_password_hash('HackFlow2026!'));db.session.add(u);people.append(u)
    db.session.flush();h=Hack(name='Актион × IT Hack 2026',description='Создаём цифровые продукты для образования. От идеи — до работающего решения в одной команде.',start=now()-timedelta(days=1),deadline=now()+timedelta(days=7),owner=people[2].id);db.session.add(h);db.session.flush()
    for u in people[:2]:db.session.add(Admission(hack_id=h.id,email=u.email))
    c=Case(hack_id=h.id,title='Единая среда студенческого хакатона',body='Разработайте платформу, объединяющую командную работу, обучение и сдачу проекта. Заказчик: Актион. Результат: работающий MVP и презентация.');db.session.add(c);db.session.flush()
    t=Team(hack_id=h.id,name='Двоичный код',captain=people[0].id,case_id=c.id,code='HACKFLOW-DEMO');db.session.add(t);db.session.flush();db.session.add(Member(user_id=people[0].id,hack_id=h.id,team_id=t.id))
    for title,status in [('Изучить проблему и интервью','done'),('Собрать прототип интерфейса','doing'),('Спроектировать REST API','review'),('Подготовить презентацию','todo')]:db.session.add(Task(team_id=t.id,title=title,status=status))
    for kind,title,body,link in [('material','Как спроектировать REST API','Документация Flask: маршруты, запросы и ответы.','https://flask.palletsprojects.com/en/stable/'),('material','React: от идеи к интерфейсу','Официальный интерактивный учебник.','https://react.dev/learn'),('event','Консультация по архитектуре','Открытые материалы консультации. Видеоссылку организатор добавит после назначения встречи.','https://developer.mozilla.org/ru/docs/Learn_web_development'),('announcement','Добро пожаловать на основной этап!','Сформируйте команду, изучите кейс и распределите задачи.','')]:db.session.add(Resource(hack_id=h.id,kind=kind,title=title,body=body,url=link,date=now()+timedelta(days=1) if kind=='event' else None))
    db.session.add(Notice(user_id=people[0].id,text='Вы допущены к основному этапу'));db.session.commit()
