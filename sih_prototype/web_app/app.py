from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_from_directory,
    redirect,
    url_for,
    flash,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    login_required,
    logout_user,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from sklearn.preprocessing import MinMaxScaler
import numpy as np
from tensorflow.keras.models import Model, load_model
from tensorflow.keras.layers import Input, LSTM, RepeatVector, TimeDistributed, Dense
from tensorflow.keras.losses import MeanSquaredError
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import os

app = Flask(__name__, static_folder="static")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///telemetry.db"
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "fallback_secret_key")
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# Load the pre-trained model
try:
    model = load_model("lstm_autoencoder.h5")
except:
    # Recreate the model architecture if loading fails
    seq_length, input_dim, latent_dim = 3, 5, 16
    inputs = Input(shape=(seq_length, input_dim))
    encoded = LSTM(latent_dim, activation="relu")(inputs)
    decoded = RepeatVector(seq_length)(encoded)
    decoded = LSTM(latent_dim, activation="relu", return_sequences=True)(decoded)
    decoded = TimeDistributed(Dense(input_dim))(decoded)
    model = Model(inputs, decoded)
    model.compile(optimizer="adam", loss=MeanSquaredError())

scaler = MinMaxScaler()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    is_officer = db.Column(db.Boolean, default=False)


class Telemetry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, nullable=False)
    water_level = db.Column(db.Float, nullable=False)
    temperature = db.Column(db.Float, nullable=False)
    rainfall = db.Column(db.Float, nullable=False)
    ph = db.Column(db.Float, nullable=False)
    dissolved_oxygen = db.Column(db.Float, nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


with app.app_context():
    db.create_all()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            flash("Logged in successfully.", "success")
            return redirect(url_for("index"))
        flash("Invalid username or password", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Username already exists", "error")
        else:
            new_user = User(
                username=username,
                password=generate_password_hash(password, method="sha256"),
            )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            flash("Registered successfully.", "success")
            return redirect(url_for("index"))
    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "success")
    return redirect(url_for("index"))


@app.route("/submit_telemetry", methods=["POST"])
@login_required
def submit_telemetry():
    data = request.json
    new_telemetry = Telemetry(
        timestamp=datetime.fromisoformat(data["timestamp"]),
        water_level=data["water_level"],
        temperature=data["temperature"],
        rainfall=data["rainfall"],
        ph=data["ph"],
        dissolved_oxygen=data["dissolved_oxygen"],
        latitude=data["latitude"],
        longitude=data["longitude"],
    )
    db.session.add(new_telemetry)
    db.session.commit()

    # Check for anomalies
    recent_data = Telemetry.query.order_by(Telemetry.timestamp.desc()).limit(3).all()
    if len(recent_data) >= 3:
        data = [
            [t.water_level, t.temperature, t.rainfall, t.ph, t.dissolved_oxygen]
            for t in reversed(recent_data)
        ]
        scaled_data = scaler.fit_transform(data)
        input_data = np.expand_dims(scaled_data, axis=0)
        reconstruction = model.predict(input_data)
        mse = np.mean(np.square(input_data - reconstruction))
        threshold = 0.1
        if mse > threshold:
            anomaly_message = f"""
            ANOMALY DETECTED
            Location: {new_telemetry.latitude}, {new_telemetry.longitude}
            Timestamp: {new_telemetry.timestamp}
            Water Level: {new_telemetry.water_level}
            Temperature: {new_telemetry.temperature}
            Rainfall: {new_telemetry.rainfall}
            pH: {new_telemetry.ph}
            Dissolved Oxygen: {new_telemetry.dissolved_oxygen}
            """
            send_email_alert(anomaly_message)
            return (
                jsonify(
                    {
                        "message": "Telemetry data submitted. Anomaly detected and reported."
                    }
                ),
                201,
            )

    return jsonify({"message": "Telemetry data submitted successfully."}), 201


@app.route("/get_dwlr_data")
def get_dwlr_data():
    subquery = (
        db.session.query(
            Telemetry.latitude,
            Telemetry.longitude,
            db.func.max(Telemetry.timestamp).label("max_timestamp"),
        )
        .group_by(Telemetry.latitude, Telemetry.longitude)
        .subquery()
    )

    latest_data = (
        db.session.query(Telemetry)
        .join(
            subquery,
            db.and_(
                Telemetry.latitude == subquery.c.latitude,
                Telemetry.longitude == subquery.c.longitude,
                Telemetry.timestamp == subquery.c.max_timestamp,
            ),
        )
        .all()
    )

    return jsonify(
        [
            {
                "lat": data.latitude,
                "lng": data.longitude,
                "water_level": data.water_level,
                "temperature": data.temperature,
                "rainfall": data.rainfall,
                "ph": data.ph,
                "dissolved_oxygen": data.dissolved_oxygen,
                "timestamp": data.timestamp.isoformat(),
            }
            for data in latest_data
        ]
    )


def send_email_alert(message):
    sender_email = os.environ.get("SENDER_EMAIL")
    receiver_email = os.environ.get("RECEIVER_EMAIL")
    password = os.environ.get("EMAIL_PASSWORD")

    if not all([sender_email, receiver_email, password]):
        app.logger.error("Email configuration is incomplete. Cannot send alert.")
        return

    msg = MIMEText(message)
    msg["Subject"] = "DWLR Anomaly Alert"
    msg["From"] = sender_email
    msg["To"] = receiver_email

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, msg.as_string())
        app.logger.info("Alert email sent successfully")
    except Exception as e:
        app.logger.error(f"Failed to send alert email: {str(e)}")


if __name__ == "__main__":
    app.run(debug=True)
