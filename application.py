import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
from functools import reduce
from botocore.exceptions import ClientError
from flask import Flask, render_template, request, redirect, url_for, session, abort

application = Flask(__name__)
app = application
app.secret_key = os.urandom(24)
app.debug = True


# Configure boto3 client
boto3.setup_default_session(region_name='ap-southeast-2')
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
users_table = dynamodb.Table('users')
bucket_name = 'dnd-app-bucket'

def upload_pfp_to_s3(file, bucket_name, acl="public-read"):
    try:
        s3.upload_fileobj(
            file,
            bucket_name,
            f"user_pfp/{file.filename}",
            ExtraArgs={
                "ACL": acl,
                "ContentType": file.content_type
            }
        )
    except Exception as e:
        print("Something Happened: ", e)
        return e

    return f"https://{bucket_name}.s3.amazonaws.com/user_pfp/{file.filename}"

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

    if 'pfp_url' in request.files:
        file = request.files['pfp_url']
        if file.filename != '': # File selected
            pfp_url = upload_pfp_to_s3(file, bucket_name)
        else: # No file selected
            pfp_url = 'https://dnd-app-bucket.s3.ap-southeast-2.amazonaws.com/user_pfp/default_pfp.jpg'
    else: # No file field in the form
        pfp_url = 'https://dnd-app-bucket.s3.ap-southeast-2.amazonaws.com/user_pfp/default_pfp.jpg'

    # Check if the email already exists in the DynamoDB table
    response = users_table.scan(FilterExpression=Attr('email').eq(email))
    if response.get('Items'):
        error_message = "Sorry! That email is already in use"
        return render_template('register.html', error_message=error_message)

    # Check if the username already exists in the DynamoDB table
    response = users_table.scan(FilterExpression=Attr('username').eq(username))
    if response.get('Items'):
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
            'pfp_url': pfp_url
        }
    )

    return redirect(url_for('index', success_message='Registration successful!'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    # success_message = request.args.get('success_message')

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        print("DEBUG: username =", username)  # Debug line

        # try:
        #     response = users_table.get_item(Key={'username': username})
        # except ClientError as e:
        #     print(e.response['Error']['Message'])
        #     error_message = "There was an error logging in. Please try again."
        #     return render_template('login.html', error_message=error_message)

        response = users_table.get_item(Key={'username': username})
        if 'Item' not in response or response['Item']['password'] != password:
            error_message = "Incorrect username or password."
            return render_template('login.html', error_message=error_message)
        session['username'] = username
        return redirect(url_for('main'))
    # return render_template('login.html', error_message=None, success_message=success_message)

@app.route('/main')
def main():
    if 'username' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['username']
    response = users_table.get_item(Key={'username': username})
    if 'Item' not in response:
        abort(403)  # Forbidden, user not logged in

    user = response['Item']

    # You can now use the 'user' variable in the render_template function.
    # ...

    return render_template('main.html')
