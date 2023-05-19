import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
from functools import reduce
from botocore.exceptions import ClientError
from flask import Flask, render_template, request, redirect, url_for, session, abort

application = Flask(__name__)
app = application
app.secret_key = os.urandom(24)

# Configure boto3 client
boto3.setup_default_session(region_name='ap-southeast-2')
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
users_table = dynamodb.Table('users')
bucket_name = 'dnd-app-bucket'

@app.errorhandler(403)
def forbidden(e):
    return render_template('forbidden.html'), 403

@app.route('/')
def index():
    success_message = request.args.get('success_message')
    return render_template('login.html', success_message=success_message)

@app.route('/register')
def register():
    return render_template('register.html')

@app.route('/register_user', methods=['GET', 'POST'])
def register_user():
    username = request.form['username']
    display_name = request.form['display_name']
    email = request.form['email']
    password = request.form['password']
    confirm_password = request.form['confirm_password']

    # Check if the email already exists in the DynamoDB table
    response = users_table.get_item(Key={'email': email})
    if 'Item' in response:
        error_message = "Sorry! That email is already in use"
        return render_template('register.html', error_message=error_message)
    
    # Check if the username already exists in the DynamoDB table
    response = users_table.get_item(Key={'username': username})
    if 'Item' in response:
        error_message = "Sorry! That username is already in use"
        return render_template('register.html', error_message=error_message)
    
    # Check if the passwords match
    if password != confirm_password:
        error_message = "Sorry! Passwords do not match"
        return render_template('register.html', error_message=error_message)

    users_table.put_item(
        Item={
            'username': username,
            'display_name': display_name,
            'email': email,
            'password': password,
        }
    )

    return redirect(url_for('index', success_message='Registration successful!'))

