from email.policy import default
from enum import unique
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
import requests

from flask_apscheduler import APScheduler

import base64
import json
import datetime

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
app.secret_key = "e810f07d51812b79f9036db9d601aa4488104cc5115c9eed5704394cacf0a063"
db = SQLAlchemy(app)
admin = Admin(app, name="v2ray_sub", template_mode="bootstrap3")

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

class User(db.Model):
    
    __tablename__ = "user"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    uid = db.Column(db.Integer, nullable=False, unique=True)
    uuid = db.Column(db.String(80), unique=True, nullable=False)
    comment = db.Column(db.Text)
    expiredatetime = db.Column(db.DateTime, default=datetime.datetime.now)
    enable = db.Column(db.Boolean, default=True)
    level = db.Column(db.Integer, default=1)
    def __repr__(self) -> str:
        return "uid %s, uuid %s" % (self.uid, self.uuid)

class Node(db.Model):
    
    __tablename__ = "node"
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    level = db.Column(db.Integer, default=1)
    scheme = db.Column(db.String(64), nullable=False)
    link = db.Column(db.String(1024), nullable=False)
    
    subscribe_id = db.Column(db.Integer, db.ForeignKey("subscribe.id"))
    subscribe = db.relationship("Subscribe", backref=db.backref("nodes", lazy="dynamic"))
    
class Subscribe(db.Model):
    
    __tablename__ = 'subscribe'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    link = db.Column(db.String(1024), nullable=False)
    level = db.Column(db.Integer, default=1)
    auto_update = db.Column(db.Boolean, default=False)

admin.add_view(ModelView(User, db.session))
admin.add_view(ModelView(Node, db.session))
admin.add_view(ModelView(Subscribe, db.session))

def build_subscribe(nodes, msg):
    for node in nodes:
        if(node.scheme=="vmess"):
            link = json.loads(node.link)
            link['ps'] = msg
            link = str(link)
            # link = base64.b64encode(bytes(link, encoding="utf-8"))
        elif(node.scheme=="ss"):
            link = node.link
        encoded_link = str(base64.b64encode(bytes(link, encoding="utf-8")), encoding="utf-8")
        if(node.scheme=="vmess"):
            n = "%s://%s" % (node.scheme, encoded_link)
        elif(node.scheme=="ss"):
            n = "%s://%s#%s" % (node.scheme, encoded_link, msg)
        yield n
        
@app.route("/sub/<string:uuid>/<int:uid>")
def sub(uuid, uid):
    user = User.query.filter_by(uid=uid, uuid=uuid).first()

    if(user is None):
        msg = "用户不存在"
        nodes = Node.query.filter_by(level=7).all()
        return str(base64.b64encode(bytes("\n".join(build_subscribe(nodes, msg)), encoding="utf-8")), encoding="utf-8")
    elif(user.expiredatetime<datetime.datetime.now()):
        msg = "用户%s已过期" % user.uid
        nodes = Node.query.filter_by(id=7).all()
        return str(base64.b64encode(bytes("\n".join(build_subscribe(nodes, msg)), encoding="utf-8")), encoding="utf-8")
    elif(user.enable==False):
        msg = "用户%s已被禁用" % user.uid
        nodes = Node.query.filter_by(id=7).all()
        return str(base64.b64encode(bytes("\n".join(build_subscribe(nodes, msg)), encoding="utf-8")), encoding="utf-8")
    elif(user.enable==True):
        nodes = Node.query.filter(Node.level<=user.level).all()
        msg = "用户%s到期时间：%s" % (user.uid, user.expiredatetime.strftime("%Y-%m-%d"))
        return str(base64.b64encode(bytes("\n".join(build_subscribe(nodes, msg)), encoding="utf-8")), encoding="utf-8")



def parse_subscribe(text):
    for scheme, link in list(map(lambda x:x.split("://") ,str(base64.b64decode(text), 'utf-8').split('\n'))):
        link = bytes(link.split("#")[0], encoding='utf-8')
        missing_padding = len(link) % 4
        if missing_padding:
            link += b'='* (4 - missing_padding)
        link = str(base64.b64decode(link), encoding='utf-8')
        yield (scheme, link)

@app.route("/update")
def update():
    count = update_subscribe()

    return json.dumps({"ret": 0, "msg": "update %s"%count})


@scheduler.task("interval", hours=1)
def update_subscribe():
    subscribes = Subscribe.query.filter(Subscribe.auto_update==True).all()
    count = 0
    for subscribe in subscribes:
        # nodes = Node.query.filter_by(subscribe_id=subscribe.id).all()
        for node in subscribe.nodes:
            db.session.delete(node)
        db.session.commit()
        res = requests.get(subscribe.link)
        for scheme, link in parse_subscribe(res.text):
            db.session.add(Node(scheme=scheme, link=str(link), subscribe_id=subscribe.id, level=subscribe.level))
        db.session.commit()
        count += 1
    return count
        