from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
from io import BytesIO
import os
import random
from functools import wraps
from bson import ObjectId


# Initialize the Flask app
app = Flask(__name__)

# MongoDB Configuration
app.config["MONGO_URI"] = "mongodb://localhost:27017/gamehaven"  # Database 'gamehaven' on local machine
app.config["SECRET_KEY"] = 'your_secret_key'  # Secret key for session management
app.config["UPLOAD_FOLDER"] = 'static/profile_pics'  # Folder to save profile pictures uploaded by users
app.config['SESSION_COOKIE_SECURE'] = True  # Ensure cookies are transmitted only over HTTPS in production

# Initialize PyMongo
mongo = PyMongo(app)

# Allowed extensions for profile picture uploads
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Helper function to check file extensions (only allow certain image types)
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Helper function to validate image files
def is_valid_image(file):
    try:
        img = Image.open(BytesIO(file.read()))
        img.verify()  # Verify it's a valid image
        file.seek(0)  # Reset file pointer after reading
        return True
    except Exception:
        return False

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # Save the requested URL as 'next' and redirect to the login page
            next_page = request.url  # Save the original URL
            return redirect(url_for('login', next=next_page))
        return f(*args, **kwargs)
    return decorated_function

# Route to setup the database with a test user
@app.route('/setup_db')
def setup_db():
    try:
        test_user = {
            "username": "testuser",
            "full_name": "Test User",
            "email": "testuser@example.com",
            "password": generate_password_hash("testpassword"),  # Hashed password for security
            "profile_pic": "static/profile_pics/default.jpg"  # Default profile picture
        }

        # Check if the test user already exists
        if mongo.db.users.find_one({"username": "testuser"}):
            return "Database already initialized!", 200

        # Insert the test user into MongoDB
        mongo.db.users.insert_one(test_user)
        return "Database and 'users' collection initialized successfully!", 200

    except Exception as e:
        return f"Error initializing database: {str(e)}", 500

# Route to the homepage
@app.route('/')
def index():
    return render_template('index.html')

# Route to signup a new user
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        full_name = request.form.get('full_name')
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')

        # Check if passwords match
        if password != password_confirm:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('signup'))

        # Hash the password
        hashed_password = generate_password_hash(password)

        # Handle profile picture upload (if provided)
        profile_pic = None
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            if file and allowed_file(file.filename) and is_valid_image(file):
                filename = secure_filename(file.filename)
                profile_pic = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(profile_pic)
            else:
                flash('Invalid image file uploaded!', 'danger')
                return redirect(url_for('signup'))
        else:
            # If no picture is uploaded, use a random default one
            default_pics = os.listdir('static/profile_pics')
            profile_pic = os.path.join(app.config['UPLOAD_FOLDER'], random.choice(default_pics))

        # Create a new user dictionary
        user = {
            'username': username,
            'full_name': full_name,
            'email': email,
            'password': hashed_password,  # Store the hashed password
            'profile_pic': profile_pic
        }

        # Check if the user already exists
        existing_user = mongo.db.users.find_one({'username': username})
        if existing_user:
            flash('Username already exists!', 'danger')
            return redirect(url_for('signup'))

        # Insert the new user into the database
        mongo.db.users.insert_one(user)
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))
    
    return render_template('sign_up.html')

# Route to login a user
@app.route('/login', methods=['GET', 'POST'])
def login():
    next_page = request.args.get('next')  # Get the 'next' parameter from the URL
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Validate that username and password are not None
        if not username or not password:
            flash('Username and password are required!', 'danger')
            return redirect(url_for('login', next=next_page))

        # Find the user in the database
        user = mongo.db.users.find_one({'username': username})

        # Check if the user exists and the password matches
        if user and check_password_hash(user['password'], password):
            # Store user information in the session
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['profile_pic'] = user['profile_pic']

            # Redirect to the next page if available, or fallback to the profile page
            return redirect(next_page or url_for('profile'))

        # Failed login: Flash a message and redirect to login page
        flash('Invalid username or password!', 'danger')
        return redirect(url_for('login', next=next_page))

    # Render the login page, passing the next parameter
    return render_template('login.html', next=next_page)



# Route for logging out (clears the session)
@app.route('/logout')
def logout():
    session.clear()  # Clears session data
    flash('You have been logged out successfully!', 'info')
    return redirect(url_for('login'))  # Redirect to login page

# Route for the user's profile page
@app.route('/profile')
@login_required
def profile():
    # Fetch user details from the session
    user = mongo.db.users.find_one({"_id": ObjectId(session['user_id'])})
    profile_pic = session['profile_pic'].replace("\\", "/")
    
    return render_template(
        'profile.html',
        username=session['username'],
        full_name=user['full_name'],
        email=user['email'],
        profile_pic=profile_pic
    )

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    # Fetch current user details from MongoDB
    user = mongo.db.users.find_one({"_id": ObjectId(session['user_id'])})
    
    if request.method == 'POST':
        # Update the user's details
        updated_details = {
            "full_name": request.form.get('full_name', user['full_name']),
            "email": request.form.get('email', user['email']),
            "phone": request.form.get('phone', user.get('phone', '')),
            "address": request.form.get('address', user.get('address', '')),
            "dob": request.form.get('dob', user.get('dob', '')),
        }

        # Update the user in the database
        mongo.db.users.update_one({"_id": ObjectId(session['user_id'])}, {"$set": updated_details})
        flash("Profile updated successfully!", "success")
        return redirect(url_for('profile'))

    return render_template('edit_profile.html', user=user)


# Route for dynamic game pages (requires login)
@app.route('/<page_name>')
@login_required  # Protect game pages so only logged-in users can access them
def show_page(page_name):
    # List of valid game pages
    pages = ['index', 'unloadedgame', 'memory_game', 'mazegame', 'tictactoe', 'balloon_popper', 'minesweeper', 'whack_a_mole', 'pacman', 'tetris', 'snake_game', 'bubble_shooter', 'sudoku', 'trail', 'tower_blocks', 'flappy_bird', 'darkwood_dash', 'connect4']
    
    # Check if the requested page is in the valid list of pages
    if page_name in pages:
        return render_template(f'{page_name}.html')  # Render the page template
    else:
        return "Page not found", 404  # Return a 404 error if page not found

# Custom error handlers
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('500.html'), 500

# Navbar pages
@app.route('/about_us')
def about_us():
    return render_template('about_us.html')

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/help')
def help():
    return render_template('help.html')

@app.route('/contact_us')
@login_required
def contact_us():
    return render_template('contact_us.html')

@app.route('/feedback')
@login_required
def feedback():
    return render_template('feedback.html')



# Run the app
if __name__ == '__main__':
    app.run(debug=True)
