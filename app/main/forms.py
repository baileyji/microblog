from flask import request
from flask_wtf import FlaskForm
import wtforms
from wtforms import StringField, SubmitField, TextAreaField, BooleanField, FormField
from wtforms.validators import ValidationError, DataRequired, Length, NumberRange
from flask_babel import _, lazy_gettext as _l
from ..models import User

import wtforms.widgets.html5
import wtforms.fields.html5
from wtforms.fields.html5 import DecimalRangeField


class CloudControl(FlaskForm):
    speaker_connected = BooleanField()
    muted = BooleanField()


class EmptyForm(FlaskForm):
    submit = SubmitField('Submit')
