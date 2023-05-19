from flask import Flask, render_template, request, redirect
import boto3


application = Flask(__name__)
app = application

# Configure boto3 client
boto3.setup_default_session(region_name='ap-southeast-2')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('users')

s3 = boto3.client('s3')
bucket_name = 'dnd-app-bucket'

def create_new_user(username, display_name, email, password, pfp_url):
    table.put_item(
       Item={
            'username': username,
            'display_name': display_name,
            'email': email,
            'password': password,
            'pfp_url': pfp_url
        }
    )

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
def home():
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        display_name = request.form['display_name']
        email = request.form['email']
        password = request.form['password']
        
        file = request.files['pfp_url']
        if file.filename == '': # No file selected
            pfp_url = 'https://dnd-app-bucket.s3.ap-southeast-2.amazonaws.com/user_pfp/default_pfp.jpg'
        else:
            pfp_url = upload_pfp_to_s3(file, bucket_name)
        
        table.put_item(
           Item={
                'username': username,
                'display_name': display_name,
                'email': email,
                'password': password,
                'pfp_url': pfp_url
            }
        )

        return redirect('/')
    
    return render_template('register.html')
