from flask import Flask, render_template, request, redirect, session, url_for, flash
import pyrebase
import requests
import secrets
import cloudinary
import cloudinary.uploader
from PIL import Image
from io import BytesIO
import google.generativeai as genai
from math import ceil


# ---------------- GEMINI ----------------
genai.configure(api_key="AIzaSyB4XHbXUUs4tNJC8M-q4j9ry-XoLutR6Sw")


# ---------------- FLASK ----------------
app = Flask(__name__)
app.secret_key = secrets.token_hex(24)


# ---------------- FIREBASE CONFIG ----------------
firebaseConfig = {
    "apiKey": "AIzaSyDpmQarhCbP-71pAOvKsWYZmB4d9piXBxY",
    "authDomain": "image-processing-5ec16.firebaseapp.com",
    "databaseURL": "https://image-processing-5ec16-default-rtdb.asia-southeast1.firebasedatabase.app",
    "projectId": "image-processing-5ec16",
    "storageBucket": "image-processing-5ec16.appspot.com",
    "messagingSenderId": "851294956077",
    "appId": "1:851294956077:web:97112c212b35c667ed26a4"
}

firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()
db = firebase.database()


# ---------------- CLOUDINARY ----------------
cloudinary.config(
    cloud_name='di0hj80po',
    api_key='546682773794724',
    api_secret='NyOjpoNYBhWgg7bE7xPhoa5rFS8'
)


# ---------------- GEMINI FUNCTION ----------------
def generate_description_with_gemini(image_url):
    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        image_bytes = requests.get(image_url).content

        response = model.generate_content([
            "Describe this image",
            {"mime_type": "image/jpeg", "data": image_bytes}
        ])

        return response.text.strip()

    except Exception as e:
        print("Gemini error:", e)
        return "Auto description failed"


# ---------------- HOME ----------------
@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('main'))
    return redirect(url_for('login'))


# ---------------- SIGNUP ----------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():

    if request.method == 'POST':

        email = request.form.get('email')
        password = request.form.get('password')

        if not email or not password:
            flash("Email & Password required", "danger")
            return render_template('authentication.html')

        try:
            user = auth.create_user_with_email_and_password(email, password)
            user_id = user['localId']

            db.child("users").child(user_id).set({
                "email": email
            })

            flash("Signup successful! Login now", "success")
            return redirect(url_for('login'))

        except requests.exceptions.HTTPError as e:

            try:
                error_message = e.response.json()['error']['message']
            except:
                error_message = str(e)

            if error_message == "EMAIL_EXISTS":
                flash("Email already exists", "danger")

            elif "WEAK_PASSWORD" in error_message:
                flash("Password must be 6+ characters", "danger")

            else:
                flash(error_message, "danger")

    return render_template('authentication.html')


# ---------------- LOGIN ----------------
@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form.get('email')
        password = request.form.get('password')

        try:
            user = auth.sign_in_with_email_and_password(email, password)

            session['user'] = {
                "localId": user['localId'],
                "idToken": user['idToken'],
                "email": email
            }

            return redirect(url_for('main'))

        except requests.exceptions.HTTPError as e:

            try:
                error_message = e.response.json()['error']['message']
            except:
                error_message = str(e)

            if error_message == "EMAIL_NOT_FOUND":
                flash("Email not registered", "danger")

            elif error_message == "INVALID_PASSWORD":
                flash("Wrong password", "danger")

            else:
                flash(error_message, "danger")

    return render_template('authentication.html')


# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ---------------- MAIN DASHBOARD ----------------
@app.route('/main')
def main():

    if 'user' not in session:
        return redirect(url_for('login'))

    user_id = session['user']['localId']

    try:
        data = db.child("users").child(user_id).child("images").get(session['user']['idToken']).val()
        images = list(data.values()) if data else []
    except:
        images = []

    return render_template('main.html', images=images)


# ---------------- STORE IMAGE ----------------
@app.route('/store', methods=['GET', 'POST'])
def store_new_image_record():

    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':

        title = request.form.get('imageTitle')
        description = request.form.get('imageDescription')
        file = request.files.get('imageUpload')

        if not title or not file:
            flash("Title & Image required", "danger")
            return redirect(url_for('store_new_image_record'))

        try:
            image = Image.open(file.stream)
            image.thumbnail((800, 600))

            buffer = BytesIO()
            image.save(buffer, format="JPEG")
            buffer.seek(0)

            upload = cloudinary.uploader.upload(buffer)
            image_url = upload['secure_url']

        except Exception as e:
            flash("Upload failed: " + str(e), "danger")
            return redirect(url_for('store_new_image_record'))

        if not description.strip():
            description = generate_description_with_gemini(image_url)

        db.child("users").child(session['user']['localId']).child("images").push({
            "title": title,
            "description": description,
            "image_url": image_url
        }, session['user']['idToken'])

        return redirect(url_for('main'))

    return render_template('store_new_image_record.html')


# ---------------- VIEW IMAGES ----------------
@app.route('/view')
def view_uploaded_images():

    if 'user' not in session:
        return redirect(url_for('login'))

    user_id = session['user']['localId']
    page = int(request.args.get('page', 1))
    per_page = 9

    data = db.child("users").child(user_id).child("images").get(session['user']['idToken']).val()

    images = []
    if data:
        for k, v in data.items():
            v['id'] = k
            images.append(v)

    total_pages = ceil(len(images) / per_page)
    paginated = images[(page - 1) * per_page: page * per_page]

    return render_template("view_uploaded_image.html",
                           images=paginated,
                           total_pages=total_pages)


# ---------------- DELETE IMAGE ----------------
@app.route('/image/<image_id>/delete', methods=['POST'])
def delete_image(image_id):

    if 'user' not in session:
        return redirect(url_for('login'))

    user_id = session['user']['localId']

    image = db.child("users").child(user_id).child("images").child(image_id).get(session['user']['idToken']).val()

    if image:
        public_id = image['image_url'].split('/')[-1].split('.')[0]
        cloudinary.uploader.destroy(public_id)

        db.child("users").child(user_id).child("images").child(image_id).remove(session['user']['idToken'])

    return redirect(url_for('view_uploaded_images'))


# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)
