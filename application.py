import os
import boto3
import requests
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
notes_table = dynamodb.Table('notes')
characters_table = dynamodb.Table('characters')
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

def upload_characterimg_to_s3(file, bucket_name, acl="public-read"):
    try:
        s3.upload_fileobj(
            file,
            bucket_name,
            f"character_img/{file.filename}",
            ExtraArgs={
                "ACL": acl,
                "ContentType": file.content_type
            }
        )
    except Exception as e:
        print("Something Happened: ", e)
        return e

    return f"https://{bucket_name}.s3.amazonaws.com/character_img/{file.filename}"

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

@app.route('/logout')
def logout():    
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    session.pop('user', None)
    return redirect(url_for('index'))

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
        # Upload file to S3 and get the URL
        new_pfp_url = upload_pfp_to_s3(file, bucket_name) 
        users_table.update_item(
            Key={'username': session['user']['username']},
            UpdateExpression="set pfp_url = :r",
            ExpressionAttributeValues={
                ':r': new_pfp_url
            }
        )
        # Update session data
        session['user']['pfp_url'] = new_pfp_url
        session.modified = True 
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
    session.modified = True 

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
    session.modified = True 

    return render_template('profile.html', user=session['user'], success_message="Password changed successfully")

@app.route('/notes', methods=['GET'])
def notes():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    # Fetch notes from DynamoDB
    response = notes_table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key('username').eq(session['user']['username'])
    )

    notes = response['Items'] if 'Items' in response else []

    for note in notes:
        note['note_id'] = str(note['note_id'])  # Convert the 'id' field to string

    return render_template('notes.html', user=session['user'], notes=notes)

@app.route('/create_note', methods=['POST'])
def create_note():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    note_name = request.form['note_name']
    note_content = request.form['note_content']

    # Perform a scan operation to get the count of existing notes
    response = notes_table.scan(Select='COUNT')
    note_count = response['Count']

    # Generate the note ID based on the note count
    note_id = str(note_count + 1)

    # Put new note in DynamoDB table
    notes_table.put_item(
        Item={
            'username': session['user']['username'],
            'note_id': note_id,
            'note_name': note_name,
            'note_content': note_content
        }
    )

    # Redirect back to the notes page
    return redirect(url_for('notes'))  

@app.route('/edit_note', methods=['POST'])
def edit_note():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    note_id = request.form['note_id']
    note_name = request.form['note_name']
    note_content = request.form['note_content']

    # Update the note in DynamoDB table
    notes_table.update_item(
        Key={
            'username': session['user']['username'],
            'note_id': note_id
        },
        UpdateExpression='SET note_name = :note_name, note_content = :note_content',
        ExpressionAttributeValues={
            ':note_name': note_name,
            ':note_content': note_content
        }
    )

    # Redirect back to the notes page
    return redirect(url_for('notes'))  

@app.route('/character_creation', methods=['GET'])
def character_creation():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    return render_template('character_creation.html', user=session['user'])

@app.route('/create_character', methods=['POST'])
def create_character():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    # Perform a scan operation to get the count of existing notes
    response = characters_table.scan(Select='COUNT')
    characters_count = response['Count']

    # Generate the note ID based on the note count
    character_id = str(characters_count + 1)

    character = {
        'username': session['user']['username'],
        'character_id': character_id,
        'character_img': 'https://dnd-app-bucket.s3.ap-southeast-2.amazonaws.com/character_img/default_character.png',
        'character_name': request.form['character_name'],
        'character_race': request.form['character_race'],
        'character_class': request.form['character_class'],
        'ability_scores': {
            'Strength': request.form['Strength'],
            'Dexterity': request.form['Dexterity'],
            'Constitution': request.form['Constitution'],
            'Intelligence': request.form['Intelligence'],
            'Wisdom': request.form['Wisdom'],
            'Charisma': request.form['Charisma']
        },
        'character_proficiency_bonus': request.form['character_proficiency_bonus'],
        'character_hp': request.form['character_hp'],
        'character_ac': request.form['character_ac'],
        'character_alignment': request.form['character_alignment'],
        'character_skills': {
            'Acrobatics': request.form['Acrobatics'],
            'Animal Handling': request.form['AnimalHandling'],
            'Arcana': request.form['Arcana'],
            'Athletics': request.form['Athletics'],
            'Deception': request.form['Deception'],
            'History': request.form['History'],
            'Insight': request.form['Insight'],
            'Intimidation': request.form['Intimidation'],
            'Investigation': request.form['Investigation'],
            'Medicine': request.form['Medicine'],
            'Nature': request.form['Nature'],
            'Perception': request.form['Perception'],
            'Performance': request.form['Performance'],
            'Persuasion': request.form['Persuasion'],
            'Religion': request.form['Religion'],
            'Sleight of Hand': request.form['SleightOfHand'],
            'Stealth': request.form['Stealth'],
            'Survival': request.form['Survival']
        },
        'character_languages': request.form.getlist('selectedLanguages'),
        'character_spells': request.form.getlist('selectedSpells'),
        'character_equipment': request.form.getlist('selectedEquipment'),
        'character_appearance': request.form['character_appearance'],
        'character_personality_traits': request.form['character_personality_traits'],
        'character_backstory': request.form['character_backstory']
    }

    characters_table.put_item(
        Item=character
    )

    return redirect(url_for('character_selection'))

@app.route('/character_selection', methods=['GET'])
def character_selection():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['user']['username']

    # Query DynamoDB to get the characters of the current user
    response = characters_table.query(
        KeyConditionExpression=Key('username').eq(username)
    )

    # Parse characters from the response
    characters = response['Items']

    return render_template('character_selection.html', user=session['user'], characters=characters)

@app.route('/character_manage', methods=['GET'])
def character_manage():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['user']['username']

    # Query DynamoDB to get the characters of the current user
    response = characters_table.query(
        KeyConditionExpression=Key('username').eq(username)
    )

    # Parse characters from the response
    characters = response['Items']

    return render_template('character_manage.html', user=session['user'])

@app.route('/character_screen/<character_id>', methods=['GET'])
def character_screen(character_id):
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['user']['username']

    # Query DynamoDB to get the specific character by character_id
    response = characters_table.get_item(
        Key={
            'username': username,
            'character_id': character_id
        }
    )

    # Check if item found
    if 'Item' in response:
        character = response['Item']

        return render_template('character_screen.html', user=session['user'], character=character)
    else:
        abort(404)  # Not found, no character with this id

@app.route('/upload_image/<character_id>', methods=['POST'])
def upload_image(character_id):
    if 'character_image' not in request.files:
        return redirect(url_for('character_screen', character_id=character_id))

    file = request.files['character_image']

    if file.filename == '':
        return redirect(url_for('character_screen', character_id=character_id))

    if file:
        response = upload_characterimg_to_s3(file, bucket_name)
        if isinstance(response, Exception): 
            return str(response)

        # Get the URL of the uploaded file
        uploaded_file_url = response

        # Update the character's image in the database
        username = session['user']['username']
        characters_table.update_item(
            Key={
                'username': username,
                'character_id': character_id
            },
            UpdateExpression="set character_img = :r",
            ExpressionAttributeValues={
                ':r': uploaded_file_url
            },
            ReturnValues="UPDATED_NEW"
        )

    return redirect(url_for('character_screen', character_id=character_id))

@app.route('/character_equipment/<character_id>', methods=['GET'])
def character_equipment(character_id):
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['user']['username']

    # Query DynamoDB to get the specific character by character_id
    response = characters_table.get_item(
        Key={
            'username': username,
            'character_id': character_id
        }
    )

    # Check if item found
    if 'Item' in response:
        character = response['Item']

        return render_template('character_equipment.html', user=session['user'], character=character)

@app.route('/update_equipment', methods=['POST'])
def update_equipment():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['user']['username']

    # Extract character_id from the form
    character_id = request.form['character_id']

    # Get the new equipment list from the form
    new_equipment = request.form.getlist('selectedEquipment')

    # Update the character's equipment in DynamoDB
    response = characters_table.update_item(
        Key={
            'username': username,
            'character_id': character_id
        },
        UpdateExpression="set character_equipment = :e",
        ExpressionAttributeValues={
            ':e': new_equipment
        },
        ReturnValues="UPDATED_NEW"
    )

    # After updating the equipment, redirect the user back to the character page
    return redirect(url_for('character_equipment', character_id=character_id))
    
@app.route('/character_edit/<character_id>', methods=['GET'])
def character_edit(character_id):
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['user']['username']

    # Query DynamoDB to get the specific character by character_id
    response = characters_table.get_item(
        Key={
            'username': username,
            'character_id': character_id
        }
    )

    # Check if item found
    if 'Item' in response:
        character = response['Item']

        return render_template('character_edit.html', user=session['user'], character=character)

@app.route('/edit_character/<character_id>', methods=['POST'])
def edit_character(character_id):
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    character = {
        'username': session['user']['username'],
        'character_id': character_id,
        'character_name': request.form['character_name'],
        'character_race': request.form['character_race'],
        'character_class': request.form['character_class'],
        'character_alignment': request.form['character_alignment'],
        'character_languages': request.form.getlist('selectedLanguages'),
        'character_appearance': request.form['character_appearance'],
        'character_personality_traits': request.form['character_personality_traits'],
        'character_backstory': request.form['character_backstory']
    }

    characters_table.update_item(
        Key={
            'username': session['user']['username'],
            'character_id': character_id
        },
        UpdateExpression="set character_name = :n, character_race = :r, character_class = :c, character_alignment = :a, character_languages = :l, character_appearance = :ap, character_personality_traits = :p, character_backstory = :b",
        ExpressionAttributeValues={
            ':n': character['character_name'],
            ':r': character['character_race'],
            ':c': character['character_class'],
            ':a': character['character_alignment'],
            ':l': character['character_languages'],
            ':ap': character['character_appearance'],
            ':p': character['character_personality_traits'],
            ':b': character['character_backstory']
        },
        ReturnValues="UPDATED_NEW"
    )

    return redirect(url_for('character_screen', character_id=character_id))

@app.route('/character_spells/<character_id>', methods=['GET'])
def character_spells(character_id):
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['user']['username']

    # Query DynamoDB to get the specific character by character_id
    response = characters_table.get_item(
        Key={
            'username': username,
            'character_id': character_id
        }
    )

    # Check if item found
    if 'Item' in response:
        character = response['Item']

        return render_template('character_spells.html', user=session['user'], character=character)
    
@app.route('/update_spells', methods=['POST'])
def update_spells():
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['user']['username']

    # Extract character_id from the form
    character_id = request.form['character_id']

    # Get the new spells list from the form
    new_spells = request.form.getlist('selectedSpells')

    # Update the character's spells in DynamoDB
    response = characters_table.update_item(
        Key={
            'username': username,
            'character_id': character_id
        },
        UpdateExpression="set character_spells = :e",
        ExpressionAttributeValues={
            ':e': new_spells
        },
        ReturnValues="UPDATED_NEW"
    )

    # After updating the spells, redirect the user back to the character page
    return redirect(url_for('character_spells', character_id=character_id))

@app.route('/character_relationships/<character_id>', methods=['GET'])
def character_relationships(character_id):
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['user']['username']

    # Query DynamoDB to get the specific character by character_id
    response = characters_table.get_item(
        Key={
            'username': username,
            'character_id': character_id
        }
    )

    # Check if item found
    if 'Item' in response:
        character = response['Item']

        return render_template('character_relationships.html', user=session['user'], character=character)
    
@app.route('/character_party/<character_id>', methods=['GET'])
def character_party(character_id):
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['user']['username']

    # Query DynamoDB to get the specific character by character_id
    response = characters_table.get_item(
        Key={
            'username': username,
            'character_id': character_id
        }
    )

    # Check if item found
    if 'Item' in response:
        character = response['Item']

        return render_template('character_party.html', user=session['user'], character=character)

@app.route('/search_characters/<character_id>', methods=['POST'])
def search_characters(character_id):
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['user']['username']

    # Query DynamoDB to get the specific character by character_id
    response = characters_table.get_item(
        Key={
            'username': username,
            'character_id': character_id
        }
    )

    # Check if item found
    if 'Item' in response:
        character = response['Item']

    search_term = request.form['search_term']

    response = characters_table.scan(
        FilterExpression=Attr('character_name').contains(search_term)
    )

    search_results = response['Items']

    return redirect(url_for('character_party', character_id=character_id, character=character, search_results=search_results))


@app.route('/add_to_party/<character_id>/<member_id>', methods=['GET'])
def add_to_party(character_id, member_id):
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    # Fetch the character to be added
    response = characters_table.get_item(
        Key={
            'character_id': member_id
        }
    )

    # Check if item found
    if 'Item' not in response:
        abort(404)  # Not found, no character with this id

    member = response['Item']

    # Fetch the characters_table owner character
    response = characters_table.get_item(
        Key={
            'character_id': character_id
        }
    )

    if 'Item' not in response:
        abort(404)  # Not found, no character with this id

    character = response['Item']

    # Update party list
    if 'character_party' not in character:
        character['character_party'] = []

    character['character_party'].append(member['character_name'])

    # Update the character in the database
    characters_table.update_item(
        Key={
            'character_id': character_id
        },
        UpdateExpression="set character_party = :p",
        ExpressionAttributeValues={
            ':p': character['character_party']
        },
        ReturnValues="UPDATED_NEW"
    )

    return redirect(url_for('character_party', character_id=character_id))



@app.route('/character_level_up/<character_id>', methods=['GET'])
def character_level_up(character_id):
    if 'user' not in session:
        abort(403)  # Forbidden, user not logged in

    username = session['user']['username']

    # Query DynamoDB to get the specific character by character_id
    response = characters_table.get_item(
        Key={
            'username': username,
            'character_id': character_id
        }
    )

    # Check if item found
    if 'Item' in response:
        character = response['Item']

        return render_template('character_level_up.html', user=session['user'], character=character)