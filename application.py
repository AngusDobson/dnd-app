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
    success_message = request.args.get('success_message')

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        response = users_table.get_item(Key={'username': username})
        if 'Item' not in response or response['Item']['password'] != password:
            error_message = "Incorrect username or password."
            return render_template('login.html', error_message=error_message)
        session['user'] = response['Item']
        return redirect(url_for('main'))
    return render_template('login.html', error_message=None, success_message=success_message)

@app.route('/main')
def main():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    user = session['user']

    return render_template('main.html', user=user)


@app.route('/profile')
def profile():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    user = session['user']

    return render_template('profile.html', user=user)

@app.route('/update_pfp', methods=['POST'])
def update_pfp():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    file = request.files['new_pfp']
    if file:
        # Save file and get the URL, here the function save_file should be implemented by you.
        new_pfp_url = save_file(file) 
        users_table.update_item(
            Key={'username': session['user']['username']},
            UpdateExpression="set pfp_url = :r",
            ExpressionAttributeValues={
                ':r': new_pfp_url
            }
        )
        # Update session data
        session['user']['pfp_url'] = new_pfp_url
        return render_template('profile.html', user=session['user'], success_message="Profile picture updated successfully")
    return render_template('profile.html', user=session['user'], error_message="No file selected")


@app.route('/update_userinfo', methods=['POST'])
def update_userinfo():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    new_display_name = request.form['display_name']
    new_email = request.form['email']
    users_table.update_item(
        Key={'username': session['user']['username']},
        UpdateExpression="set display_name = :d, email = :e",
        ExpressionAttributeValues={
            ':d': new_display_name,
            ':e': new_email
        }
    )
    # Update session data
    session['user']['display_name'] = new_display_name
    session['user']['email'] = new_email

    return render_template('profile.html', user=session['user'], success_message="User information updated successfully")


@app.route('/change_password', methods=['POST'])
def change_password():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    old_password = request.form['old_password']
    new_password = request.form['new_password']
    confirm_new_password = request.form['confirm_new_password']

    if session['user']['password'] != old_password:
        # Old password is incorrect
        return render_template('profile.html', user=session['user'], error_message="Old password is incorrect")

    if new_password != confirm_new_password:
        # New passwords do not match
        return render_template('profile.html', user=session['user'], error_message="New passwords do not match")

    users_table.update_item(
        Key={'username': session['user']['username']},
        UpdateExpression="set password = :p",
        ExpressionAttributeValues={
            ':p': new_password
        }
    )
    # Update session data
    session['user']['password'] = new_password

    return render_template('profile.html', user=session['user'], success_message="Password changed successfully")
