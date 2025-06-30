import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'shadowstrike-secret-2025')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///shadowstrike.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Fix for Heroku/Render Postgres URL
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

# Initialize database
db = SQLAlchemy(app)

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subscription_status = db.Column(db.String(20), default='trial')
    trial_end_date = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=30))

# Trade Model
class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    symbol = db.Column(db.String(10), nullable=False)
    option_type = db.Column(db.String(4), nullable=False)  # CALL or PUT
    strike_price = db.Column(db.Float, nullable=False)
    entry_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    entry_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(10), default='open')  # open or closed
    
    user = db.relationship('User', backref='trades')

# Database initialization function
def init_database():
    try:
        with app.app_context():
            # Drop all tables and recreate (for clean start)
            db.drop_all()
            db.create_all()
            
            # Create demo admin user
            admin = User(
                username='admin',
                email='admin@shadowstrike.com',
                password_hash=generate_password_hash('admin123')
            )
            db.session.add(admin)
            
            # Create demo user
            demo = User(
                username='demo',
                email='demo@shadowstrike.com',
                password_hash=generate_password_hash('demo123')
            )
            db.session.add(demo)
            
            db.session.commit()
            logger.info("Database initialized successfully!")
            return True
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        return False

# Routes
@app.route('/')
def index():
    try:
        return render_template('welcome.html')
    except Exception as e:
        logger.error(f"Error rendering welcome.html: {e}")
        return f"""
        <!DOCTYPE html>
        <html><head><title>ShadowStrike Options</title></head>
        <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
        <h1>🎯 ShadowStrike Options</h1>
        <p>Elite Trading Platform</p>
        <p><a href="/init-db" style="color: #10b981;">Initialize Database</a> | 
        <a href="/login" style="color: #10b981;">Login</a> | 
        <a href="/register" style="color: #10b981;">Register</a> | 
        <a href="/status" style="color: #10b981;">Status</a></p>
        </body></html>
        """

@app.route('/init-db')
def initialize_database():
    success = init_database()
    if success:
        return """
        <html><body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
        <h1>✅ Database Initialized!</h1>
        <p>ShadowStrike Options database is ready!</p>
        <p><strong>Test Accounts Created:</strong></p>
        <p>Username: admin | Password: admin123</p>
        <p>Username: demo | Password: demo123</p>
        <br>
        <a href="/login" style="background: #10b981; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Go to Login</a>
        </body></html>
        """
    else:
        return """
        <html><body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
        <h1>❌ Database Initialization Failed</h1>
        <p>Check the logs for more details</p>
        <a href="/">Back to Home</a>
        </body></html>
        """

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            password = request.form.get('password')
            
            user = User.query.filter_by(username=username).first()
            
            if user and check_password_hash(user.password_hash, password):
                session['user_id'] = user.id
                session['username'] = user.username
                flash('Login successful!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password', 'error')
        except Exception as e:
            logger.error(f"Login error: {e}")
            flash('Login system error. Try initializing database first.', 'error')
    
    try:
        return render_template('login.html')
    except Exception as e:
        logger.error(f"Error rendering login.html: {e}")
        return f"""
        <!DOCTYPE html>
        <html><head><title>Login - ShadowStrike Options</title></head>
        <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; padding: 50px;">
        <div style="max-width: 400px; margin: 0 auto; background: rgba(6, 95, 70, 0.3); padding: 30px; border-radius: 15px;">
        <h1 style="color: #10b981; text-align: center;">🎯 ShadowStrike Options</h1>
        <h2 style="text-align: center;">Login</h2>
        <form method="POST">
            <div style="margin-bottom: 15px;">
                <label>Username:</label><br>
                <input name="username" style="width: 100%; padding: 10px; border-radius: 5px; border: none;" required>
            </div>
            <div style="margin-bottom: 15px;">
                <label>Password:</label><br>
                <input name="password" type="password" style="width: 100%; padding: 10px; border-radius: 5px; border: none;" required>
            </div>
            <button type="submit" style="width: 100%; padding: 12px; background: #10b981; color: white; border: none; border-radius: 5px; font-weight: bold;">Login</button>
        </form>
        <p style="text-align: center; margin-top: 20px;">
            <a href="/" style="color: #10b981;">Home</a> | 
            <a href="/register" style="color: #10b981;">Register</a> |
            <a href="/init-db" style="color: #10b981;">Initialize Database</a>
        </p>
        </div></body></html>
        """

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            terms = request.form.get('terms_accepted')
            
            # Validation
            if not all([username, email, password]):
                flash('All fields are required', 'error')
                return redirect(url_for('register'))
            
            if not terms:
                flash('You must accept the terms and conditions', 'error')
                return redirect(url_for('register'))
            
            # Check if user exists
            if User.query.filter_by(username=username).first():
                flash('Username already exists', 'error')
                return redirect(url_for('register'))
            
            if User.query.filter_by(email=email).first():
                flash('Email already registered', 'error')
                return redirect(url_for('register'))
            
            # Create new user
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
            
        except Exception as e:
            logger.error(f"Registration error: {e}")
            flash('Registration failed. Try initializing database first.', 'error')
    
    try:
        return render_template('register.html')
    except Exception as e:
        logger.error(f"Error rendering register.html: {e}")
        return f"""
        <!DOCTYPE html>
        <html><head><title>Register - ShadowStrike Options</title></head>
        <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; padding: 50px;">
        <div style="max-width: 400px; margin: 0 auto; background: rgba(6, 95, 70, 0.3); padding: 30px; border-radius: 15px;">
        <h1 style="color: #10b981; text-align: center;">🎯 ShadowStrike Options</h1>
        <h2 style="text-align: center;">Register</h2>
        <form method="POST">
            <div style="margin-bottom: 15px;">
                <label>Username:</label><br>
                <input name="username" style="width: 100%; padding: 10px; border-radius: 5px; border: none;" required>
            </div>
            <div style="margin-bottom: 15px;">
                <label>Email:</label><br>
                <input name="email" type="email" style="width: 100%; padding: 10px; border-radius: 5px; border: none;" required>
            </div>
            <div style="margin-bottom: 15px;">
                <label>Password:</label><br>
                <input name="password" type="password" style="width: 100%; padding: 10px; border-radius: 5px; border: none;" required>
            </div>
            <div style="margin-bottom: 15px;">
                <input name="terms_accepted" type="checkbox" required> I accept the terms and disclaimer
            </div>
            <button type="submit" style="width: 100%; padding: 12px; background: #10b981; color: white; border: none; border-radius: 5px; font-weight: bold;">Register</button>
        </form>
        <p style="text-align: center; margin-top: 20px;">
            <a href="/" style="color: #10b981;">Home</a> | 
            <a href="/login" style="color: #10b981;">Login</a> |
            <a href="/init-db" style="color: #10b981;">Initialize Database</a>
        </p>
        </div></body></html>
        """

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Please login to access the dashboard', 'error')
        return redirect(url_for('login'))
    
    try:
        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            flash('User not found. Please login again.', 'error')
            return redirect(url_for('login'))
        
        # Get user's trades
        trades = Trade.query.filter_by(user_id=user.id).all()
        
        # Calculate portfolio stats
        total_pnl = 0
        open_trades = 0
        for trade in trades:
            if trade.status == 'open':
                open_trades += 1
                # Simple P&L calculation (in real app, you'd get current prices)
                current_price = trade.entry_price * 1.1  # Mock 10% gain
                pnl = (current_price - trade.entry_price) * trade.quantity * 100
                total_pnl += pnl
        
        try:
            return render_template('dashboard.html', 
                                 user=user, 
                                 trades=trades, 
                                 total_pnl=total_pnl,
                                 open_trades=open_trades)
        except Exception as e:
            logger.error(f"Error rendering dashboard.html: {e}")
            return f"""
            <!DOCTYPE html>
            <html><head><title>Dashboard - ShadowStrike Options</title></head>
            <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; padding: 50px;">
            <h1 style="color: #10b981;">🎯 ShadowStrike Options - Dashboard</h1>
            <p>Welcome {user.username}! ({user.subscription_status})</p>
            <p>Portfolio P&L: ${total_pnl:.2f}</p>
            <p>Open Trades: {open_trades}</p>
            <p><a href="/logout" style="color: #ef4444;">Logout</a></p>
            </body></html>
            """
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/status')
def status():
    try:
        total_users = User.query.count()
        total_trades = Trade.query.count()
        db_status = "Connected"
    except Exception as e:
        logger.error(f"Database error in status: {e}")
        total_users = 0
        total_trades = 0
        db_status = "Not Connected"
    
    try:
        return render_template('status.html', 
                             total_users=total_users,
                             total_trades=total_trades)
    except Exception as e:
        logger.error(f"Error rendering status.html: {e}")
        return f"""
        <!DOCTYPE html>
        <html><head><title>Status - ShadowStrike Options</title></head>
        <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
        <h1 style="color: #10b981;">🎯 ShadowStrike Options - Status</h1>
        <p>Platform Status: ✅ LIVE</p>
        <p>Database Status: {db_status}</p>
        <p>Total Users: {total_users}</p>
        <p>Total Trades: {total_trades}</p>
        <br>
        <a href="/" style="color: #10b981;">Home</a> | 
        <a href="/init-db" style="color: #10b981;">Initialize Database</a>
        </body></html>
        """

# Debug route to check templates
@app.route('/debug')
def debug():
    import os
    template_dir = app.template_folder
    if os.path.exists(template_dir):
        files = os.listdir(template_dir)
        return f"Template directory exists: {template_dir}<br>Files: {files}<br><a href='/'>Home</a>"
    else:
        return f"Template directory NOT found: {template_dir}<br><a href='/'>Home</a>"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
