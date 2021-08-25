import logging
from logging.handlers import SMTPHandler, RotatingFileHandler
import os
from flask import Flask, request, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_mail import Mail
from flask_bootstrap import Bootstrap
from flask_moment import Moment
from flask_babel import Babel, lazy_gettext as _l
import cloudlight.cloudredis as cloudredis
from cloudlight.util import setup_logging
import threading
import rq
import queue
import numpy as np
# try:
from ...config import Config
from ...config import REDIS_SCHEMA
# except ValueError:
#     from config import Config

db = SQLAlchemy()
migrate = Migrate()
login = LoginManager()
login.login_view = 'auth.login'
login.login_message = _l('Please log in to access this page.')
mail = Mail()
bootstrap = Bootstrap()
moment = Moment()
babel = Babel()



def event_stream():
    for _, v in current_app.redis.listen('chat'):
        yield f'data: {v}\n\n'


def get_plot_data(redis, id, t0, t1):
    import plotly
    import plotly.express as px
    import json
    import numpy as np
    # times, vals = redis.redis_ts.read(id, t0, t1)
    times=np.arange(100)+132
    vals=np.random.uniform(size=100)
    # plot_data = [{'x': times,'y': vals,'name': title}]
    # plot_layout = {'title': title}
    # plot_config = {'responsive': True}
    # d = json.dumps(plot_data, cls=plotly.utils.PlotlyJSONEncoder)
    # l = json.dumps(plot_layout, cls=plotly.utils.PlotlyJSONEncoder)
    # c = json.dumps(plot_config, cls=plotly.utils.PlotlyJSONEncoder)

    fig = px.line(x=times, y=vals, title='Temps')
    fig.layout.datarevision = t0
    # set data_revision based on time interval
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


class MessageAnnouncer:
    def __init__(self):
        self.listeners = []

    def listen(self):
        self.listeners.append(queue.Queue(maxsize=5))
        return self.listeners[-1]

    def announce(self, msg):
        # We go in reverse order because we might have to delete an element, which will shift the
        # indices backward
        from logging import getLogger
        # getLogger(__name__).info(f'Announcing {msg}')
        for i in reversed(range(len(self.listeners))):
            try:
                self.listeners[i].put_nowait(msg)
            except queue.Full:
                del self.listeners[i]


def datagen(redis, announcer):
    import json, time
    for k, v in redis.listen(REDIS_SCHEMA['keys']):

        event = 'update'
        data = {k:v}

        # plotid = 'temp:value'
        # since = None
        # kind = 'full' if since is None else 'partial'
        # new = list(zip(*redis.range(plotid, since)))
        # data = {'id': f'redisplot:{plotid}', 'kind': kind, 'data': {'x': new[0], 'y': new[1]}}

        announcer.announce(f"event:{event}\nretry:5\ndata: {json.dumps(data)}\n\n")

    datalistener = threading.Thread(target=datagen, args=(app.redis, app.announcer), daemon=True)
    datalistener.start()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login.init_app(app)
    mail.init_app(app)
    bootstrap.init_app(app)
    moment.init_app(app)
    babel.init_app(app)
    app.redis = cloudredis.setup_redis() #Redis.from_url(app.config['REDIS_URL'])
    app.task_queue = rq.Queue('cloudlight-tasks', connection=app.redis.redis)
    # app.announcer = MessageAnnouncer()
    # datalistener = threading.Thread(target=datagen, args=(app.redis, app.announcer), daemon=True)
    # datalistener.start()

    from .errors import bp as errors_bp
    app.register_blueprint(errors_bp)

    from .auth import bp as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from .main import bp as main_bp
    app.register_blueprint(main_bp)

    from .api import bp as api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    if not app.debug and not app.testing:
        # if app.config['MAIL_SERVER']:
        #     auth = None
        #     if app.config['MAIL_USERNAME'] or app.config['MAIL_PASSWORD']:
        #         auth = (app.config['MAIL_USERNAME'],
        #                 app.config['MAIL_PASSWORD'])
        #     secure = None
        #     if app.config['MAIL_USE_TLS']:
        #         secure = ()
        #     mail_handler = SMTPHandler(
        #         mailhost=(app.config['MAIL_SERVER'], app.config['MAIL_PORT']),
        #         fromaddr='no-reply@' + app.config['MAIL_SERVER'],
        #         toaddrs=app.config['ADMINS'], subject='Cloudlight Failure',
        #         credentials=auth, secure=secure)
        #     mail_handler.setLevel(logging.ERROR)
        #     app.logger.addHandler(mail_handler)

        # if app.config['LOG_TO_STDOUT']:
        #     stream_handler = logging.StreamHandler()
        #     stream_handler.setLevel(logging.INFO)
        #     app.logger.addHandler(stream_handler)
        # else:
        #
        #     setup_logging('cloud-flask')
        #     file_handler = RotatingFileHandler('logs/microblog.log',
        #                                        maxBytes=10240, backupCount=10)
        #     file_handler.setFormatter(logging.Formatter(
        #         '%(asctime)s %(levelname)s: %(message)s '
        #         '[in %(pathname)s:%(lineno)d]'))
        #     file_handler.setLevel(logging.INFO)
        #     app.logger.addHandler(file_handler)
        #
        # app.logger.setLevel(logging.INFO)
        setup_logging('cloud-flask')
        app.logger.info('Cloudflask startup')

    return app


@babel.localeselector
def get_locale():
    return request.accept_languages.best_match(current_app.config['LANGUAGES'])

from . import models
# try:
#     from ..app import models
# except:
#     from app import models
