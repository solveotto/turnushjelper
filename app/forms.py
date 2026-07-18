from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, PasswordField, SubmitField, FloatField, IntegerField, BooleanField, FileField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, EqualTo, ValidationError, Email, Optional, Regexp
from flask_wtf.file import FileAllowed

class LoginForm(FlaskForm):
    username = StringField('Brukernavn', validators=[DataRequired(), Length(min=2, max=255)])
    password = PasswordField('Passord', validators=[DataRequired()])
    submit = SubmitField('Logg inn')
class EditUserForm(FlaskForm):
    username = StringField('Brukernavn', validators=[DataRequired(), Length(min=3, max=50)])
    name = StringField('Navn (Etternavn, Fornavn)', validators=[Optional(), Length(max=255)])
    email = StringField('E-postadresse', validators=[Optional(), Email(message='Vennligst oppgi en gyldig e-postadresse'), Length(max=255)])
    medlemsnummer = StringField('NLF-medlemsnummer', validators=[Optional(), Length(max=20)])
    rullenummer = StringField('Rullenummer', validators=[Optional(), Length(max=50)])
    stasjoneringssted = StringField('Stasjoneringssted', validators=[Optional(), Length(max=100)])
    ans_dato = StringField('Ansettelsesdato', validators=[Optional(), Regexp(r'^\d{2}\.\d{2}\.\d{4}$', message='Bruk formatet DD.MM.YYYY')])
    fodt_dato = StringField('Fødselsdato', validators=[Optional(), Regexp(r'^\d{2}\.\d{2}\.\d{4}$', message='Bruk formatet DD.MM.YYYY')])
    seniority_nr = IntegerField('Ansiennitetsnr.', validators=[Optional(), NumberRange(min=0)])
    password = PasswordField('Nytt passord (la stå tomt for å beholde nåværende)')
    confirm_password = PasswordField('Bekreft nytt passord')
    is_auth = BooleanField('Administratorrettigheter')
    email_verified = BooleanField('E-post verifisert')
    is_stub = BooleanField('Stub-bruker (ikke registrert)')
    submit = SubmitField('Oppdater bruker')

    def validate_confirm_password(self, field):
        if self.password.data and not field.data:
            raise ValidationError('Vennligst bekreft ditt nye passord.')
        if self.password.data and field.data and self.password.data != field.data:
            raise ValidationError('Passordene må være like.')

# Turnus Set Management Forms
class CreateTurnusSetForm(FlaskForm):
    name = StringField('Turnussett-navn',
                      validators=[DataRequired(), Length(min=3, max=100)],
                      render_kw={"placeholder": "f.eks. OSL Togvakter 2025"})
    year_identifier = StringField('Årsidentifikator',
                                 validators=[
                                     DataRequired(),
                                     Length(min=2, max=10),
                                     # SECURITY: this value becomes a filesystem
                                     # path component (turnusfiler/<id>/...) and is
                                     # interpolated into filenames, so restrict it
                                     # to letters/digits — blocks '.', '/', '\' and
                                     # thus path traversal (e.g. '../../etc').
                                     Regexp(r'^[A-Za-z0-9]+$',
                                            message='Kun bokstaver og tall er tillatt (f.eks. R26).'),
                                 ],
                                 render_kw={"placeholder": "f.eks. R25, R26"})
    is_active = BooleanField('Sett som aktivt turnussett')

    # File handling options
    use_existing_files = BooleanField('Bruk eksisterende filer fra turnusfiler-mappen',
                                    default=True,
                                    render_kw={"onchange": "toggleFileUploads()"})

    # Schedule upload: timeskjema (.xls TSV export) or PDF, auto-detected by content
    schedule_file = FileField('Last opp turnusfil (timeskjema .xls eller PDF)',
                        validators=[FileAllowed(['pdf', 'xls', 'tsv', 'txt'],
                                                'Kun .xls/.tsv/.txt (timeskjema) eller PDF!')])

    # Optional cross-verification source for timeskjema imports
    verify_pdf_file = FileField('Verifiserings-PDF (valgfritt)',
                        validators=[FileAllowed(['pdf'], 'Kun PDF-filer!')])

    submit = SubmitField('Opprett turnussett')

class SelectTurnusSetForm(FlaskForm):
    turnus_set = SelectField('Velg turnussett', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Bytt til valgt sett')

# User Profile Forms
class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Nåværende passord', validators=[DataRequired()])
    new_password = PasswordField('Nytt passord', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Bekreft nytt passord', validators=[DataRequired(), EqualTo('new_password')])
    submit = SubmitField('Endre passord')

# Registration Forms
class RegisterForm(FlaskForm):
    """User self-registration form"""
    username = StringField('Brukernavn (visningsnavn)', validators=[
        DataRequired(),
        Length(min=2, max=255, message='Brukernavn må være mellom 2 og 255 tegn')
    ])

    medlemsnummer = StringField('NLF-medlemsnummer', validators=[
        DataRequired(),
        Length(min=1, max=20, message='NLF-medlemsnummer er påkrevd')
    ])

    rullenummer = StringField('Rullenummer', validators=[Optional(), Length(max=10)])

    email = StringField('E-postadresse', validators=[
        DataRequired(),
        Email(message='Vennligst oppgi en gyldig e-postadresse'),
        Length(max=255)
    ])
    password = PasswordField('Passord', validators=[
        DataRequired(),
        Length(min=8, message='Passord må være minst 8 tegn')
    ])
    confirm_password = PasswordField('Bekreft passord', validators=[
        DataRequired(),
        EqualTo('password', message='Passordene må være like')
    ])
    submit = SubmitField('Registrer')

    def validate_email(self, field):
        """Custom email validation"""
        email = field.data.lower()
        # Prevent obviously fake emails
        if email.endswith('.test') or email.endswith('.invalid'):
            raise ValidationError('Vennligst bruk en gyldig e-postadresse.')

class ResendVerificationForm(FlaskForm):
    """Form to resend verification email"""
    email = StringField('E-postadresse', validators=[
        DataRequired(),
        Email()
    ])
    submit = SubmitField('Send verifiserings-e-post på nytt')


class UploadStreklisteForm(FlaskForm):
    """Form for uploading strekliste PDF"""
    pdf_file = FileField('Strekliste PDF', validators=[
        DataRequired(),
        FileAllowed(['pdf'], 'Kun PDF-filer!')
    ])
    submit = SubmitField('Last opp')


class ForgotPasswordForm(FlaskForm):
    """Form to request password reset email"""
    email = StringField('E-postadresse', validators=[
        DataRequired(),
        Email(message='Vennligst oppgi en gyldig e-postadresse')
    ])
    submit = SubmitField('Send tilbakestillingslenke')


class ResetPasswordForm(FlaskForm):
    """Form to set a new password"""
    password = PasswordField('Nytt passord', validators=[
        DataRequired(),
        Length(min=8, message='Passord må være minst 8 tegn')
    ])
    confirm_password = PasswordField('Bekreft nytt passord', validators=[
        DataRequired(),
        EqualTo('password', message='Passordene må være like')
    ])
    submit = SubmitField('Tilbakestill passord')