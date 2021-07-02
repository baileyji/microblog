#!/usr/bin/env python3
# try:
from .app import create_app, db, cli
from .app.models import User, Post, Message, Notification, Task
# except ImportError:
#     from app import create_app, db, cli
#     from app.models import User, Post, Message, Notification, Task

from ..util import setup_logging

setup_logging('cloud-cli')

app = create_app()
cli.register(app)


@app.shell_context_processor
def make_shell_context():
    return {'db': db, 'User': User, 'Post': Post, 'Message': Message,
            'Notification': Notification, 'Task': Task}


# if __name__ == '__main__':
#     app.run(host='0.0.0.0', debug=True)
