from flask import Flask, render_template

application = Flask(__name__)
app = application

@app.errorhandler(403)
def forbidden(e):
    return render_template('forbidden.html'), 403

@app.route('/')
def home():
    return render_template('login.html')
