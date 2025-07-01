import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import logging
import yfinance as yf
import requests
from flask_mail import Mail, Message
import threading
import stripe

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'shadowstrike-secret-2025')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///shadowstrike.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Email Configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('EMAIL_USERNAME', 'your-email@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASSWORD', 'your-app-password')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('EMAIL_USERNAME', 'your-email@gmail.com')

# Payment Configuration
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_demo_key')
app.config['STRIPE_PUBLIC_KEY'] = os.environ.get('STRIPE_PUBLIC_KEY', 'pk_test_demo_key')

# Fix for Heroku/Render Postgres URL
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

# Initialize extensions
db = SQLAlchemy(app)
mail = Mail(app)

# User Model (Enhanced with payment fields)
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Subscription fields
    subscription_status = db.Column(db.String(20), default='trial')
    trial_end_date = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=30))
    subscription_start_date = db.Column(db.DateTime, nullable=True)
    subscription_end_date = db.Column(db.DateTime, nullable=True)
    
    # Payment fields
    stripe_customer_id = db.Column(db.String(100), nullable=True)
    stripe_subscription_id = db.Column(db.String(100), nullable=True)
    payment_method = db.Column(db.String(20), nullable=True)
    last_payment_date = db.Column(db.DateTime, nullable=True)
    
    # Email Alert Preferences
    email_alerts_enabled = db.Column(db.Boolean, default=True)
    daily_picks_email = db.Column(db.Boolean, default=True)
    portfolio_alerts = db.Column(db.Boolean, default=True)
    market_alerts = db.Column(db.Boolean, default=True)
    email_verified = db.Column(db.Boolean, default=False)
    
    def days_left_in_trial(self):
        if self.subscription_status != 'trial':
            return 0
        delta = self.trial_end_date - datetime.utcnow()
        return max(0, delta.days)
    
    def is_subscription_active(self):
        if self.subscription_status == 'trial':
            return datetime.utcnow() < self.trial_end_date
        return self.subscription_status == 'active'

# Trade Model
class Trade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    symbol = db.Column(db.String(10), nullable=False)
    option_type = db.Column(db.String(4), nullable=False)
    strike_price = db.Column(db.Float, nullable=False)
    entry_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    entry_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(10), default='open')
    
    user = db.relationship('User', backref='trades')

# Payment Transaction Model
class PaymentTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=False)
    payment_method = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD')
    status = db.Column(db.String(20), nullable=False)
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.String(200), nullable=True)
    
    user = db.relationship('User', backref='payment_transactions')

# Email Alert Model
class EmailAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    alert_type = db.Column(db.String(50), nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    subject = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=True)
    
    user = db.relationship('User', backref='email_alerts')

# Email Functions
def send_email_async(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
            logger.info(f"Email sent successfully to {msg.recipients}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")

def send_welcome_email(user_email, username):
    try:
        msg = Message(
            subject="🎯 Welcome to ShadowStrike Options!",
            recipients=[user_email],
            html=f"""
            <html>
            <body style="font-family: Arial; background: #1f2937; color: white; padding: 40px;">
                <div style="max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #065f46, #10b981); padding: 30px; border-radius: 15px;">
                    <h1 style="color: #ffffff; text-align: center;">🎯 Welcome to ShadowStrike Options!</h1>
                    <h2>Hello {username}!</h2>
                    <p>Your 30-day free trial has begun! After your trial, continue for just $49/month.</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://shadowstrike-options-2025.onrender.com/login" style="background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                            Access Your Dashboard
                        </a>
                    </div>
                </div>
            </body>
            </html>
            """
        )
        
        thread = threading.Thread(target=send_email_async, args=(app, msg))
        thread.start()
        return True
    except Exception as e:
        logger.error(f"Error sending welcome email: {e}")
        return False

# Market Data Functions
def get_stock_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.info
        current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('previousClose')
        return {
            'symbol': symbol,
            'price': round(current_price, 2) if current_price else 0,
            'change': round(info.get('regularMarketChange', 0), 2),
            'change_percent': round(info.get('regularMarketChangePercent', 0), 2),
            'volume': info.get('volume', 0),
            'market_cap': info.get('marketCap', 0)
        }
    except Exception as e:
        logger.error(f"Error getting price for {symbol}: {e}")
        return {'symbol': symbol, 'price': 0, 'change': 0, 'change_percent': 0, 'volume': 0, 'market_cap': 0}

def get_market_status():
    try:
        now = datetime.now()
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        
        is_weekday = now.weekday() < 5
        is_market_hours = market_open <= now <= market_close
        
        return {
            'is_open': is_weekday and is_market_hours,
            'status': 'OPEN' if (is_weekday and is_market_hours) else 'CLOSED',
            'next_open': 'Monday 9:30 AM ET' if now.weekday() >= 5 else 'Tomorrow 9:30 AM ET'
        }
    except:
        return {'is_open': False, 'status': 'UNKNOWN', 'next_open': 'Unknown'}

def get_top_movers():
    symbols = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL']
    movers = []
    
    for symbol in symbols:
        try:
            data = get_stock_price(symbol)
            if data['price'] > 0:
                movers.append(data)
        except:
            continue
    
    movers.sort(key=lambda x: abs(x['change_percent']), reverse=True)
    return movers[:5]

def calculate_option_probability(stock_price, strike_price, days_to_expiry, option_type='CALL'):
    try:
        if days_to_expiry <= 0:
            return 0
        
        price_ratio = stock_price / strike_price
        time_factor = days_to_expiry / 365
        
        if option_type == 'CALL':
            if price_ratio >= 1:
                base_prob = 60 + (price_ratio - 1) * 30
            else:
                base_prob = 40 * price_ratio
        else:
            if price_ratio <= 1:
                base_prob = 60 + (1 - price_ratio) * 30
            else:
                base_prob = 40 / price_ratio
        
        time_adjusted = base_prob * (1 + time_factor * 0.5)
        return min(95, max(5, round(time_adjusted, 1)))
    except:
        return 50

# Access Control Decorator
def subscription_required(f):
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this feature', 'error')
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or not user.is_subscription_active():
            flash('Your trial has expired. Please subscribe to continue using ShadowStrike Options.', 'error')
            return redirect(url_for('subscribe'))
        
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

# Database initialization function
def init_database():
    try:
        with app.app_context():
            db.drop_all()
            db.create_all()
            
            # Create demo admin user
            admin = User(
                username='admin',
                email='admin@shadowstrike.com',
                password_hash=generate_password_hash('admin123'),
                email_verified=True,
                subscription_status='active',
                subscription_start_date=datetime.utcnow(),
                subscription_end_date=datetime.utcnow() + timedelta(days=365)
            )
            db.session.add(admin)
            
            # Create demo user with trial
            demo = User(
                username='demo',
                email='demo@shadowstrike.com',
                password_hash=generate_password_hash('demo123'),
                email_verified=True,
                subscription_status='trial',
                trial_end_date=datetime.utcnow() + timedelta(days=25)
            )
            db.session.add(demo)
            
            # Add demo trades
            demo_trades = [
                Trade(user_id=2, symbol='AAPL', option_type='CALL', strike_price=180, 
                      entry_price=2.50, quantity=5, entry_date=datetime.now() - timedelta(days=5)),
                Trade(user_id=2, symbol='MSFT', option_type='PUT', strike_price=420, 
                      entry_price=8.20, quantity=2, entry_date=datetime.now() - timedelta(days=3)),
                Trade(user_id=2, symbol='TSLA', option_type='CALL', strike_price=250, 
                      entry_price=12.80, quantity=1, entry_date=datetime.now() - timedelta(days=1))
            ]
            
            for trade in demo_trades:
                db.session.add(trade)
            
            db.session.commit()
            logger.info("Database initialized successfully with payment system!")
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
        <p>Elite Trading Platform with Payment Processing</p>
        <p><a href="/init-db" style="color: #10b981;">Initialize Database</a> | 
        <a href="/login" style="color: #10b981;">Login</a> | 
        <a href="/register" style="color: #10b981;">Register</a></p>
        </body></html>
        """

@app.route('/init-db')
def initialize_database():
    success = init_database()
    if success:
        return """
        <html><body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
        <h1>✅ Database Initialized!</h1>
        <p>ShadowStrike Options database ready with payment system!</p>
        <p><strong>Test Accounts:</strong></p>
        <p>Username: admin | Password: admin123 (Active subscription)</p>
        <p>Username: demo | Password: demo123 (25 days trial left)</p>
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
            <a href="/register" style="color: #10b981;">Register</a>
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
            
            if not all([username, email, password]):
                flash('All fields are required', 'error')
                return redirect(url_for('register'))
            
            if not terms:
                flash('You must accept the terms and conditions', 'error')
                return redirect(url_for('register'))
            
            if User.query.filter_by(username=username).first():
                flash('Username already exists', 'error')
                return redirect(url_for('register'))
            
            if User.query.filter_by(email=email).first():
                flash('Email already registered', 'error')
                return redirect(url_for('register'))
            
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()
            
            send_welcome_email(email, username)
            
            flash('Registration successful! Check your email for welcome message.', 'success')
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
            <button type="submit" style="width: 100%; padding: 12px; background: #10b981; color: white; border: none; border-radius: 5px; font-weight: bold;">Start 30-Day Trial</button>
        </form>
        <p style="text-align: center; margin-top: 20px;">
            <a href="/" style="color: #10b981;">Home</a> | 
            <a href="/login" style="color: #10b981;">Login</a>
        </p>
        </div></body></html>
        """

@app.route('/dashboard')
@subscription_required
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
        
        # Show trial warning if less than 7 days left
        if user.subscription_status == 'trial' and user.days_left_in_trial() <= 7:
            flash(f'Your trial expires in {user.days_left_in_trial()} days. Subscribe now to keep access!', 'warning')
        
        market_status = get_market_status()
        top_movers = get_top_movers()
        trades = Trade.query.filter_by(user_id=user.id).all()
        
        total_pnl = 0
        open_trades = 0
        enhanced_trades = []
        
        for trade in trades:
            if trade.status == 'open':
                open_trades += 1
                stock_data = get_stock_price(trade.symbol)
                current_stock_price = stock_data['price']
                
                days_to_expiry = 30
                probability = calculate_option_probability(
                    current_stock_price, trade.strike_price, days_to_expiry, trade.option_type
                )
                
                if trade.option_type == 'CALL':
                    intrinsic_value = max(0, current_stock_price - trade.strike_price)
                else:
                    intrinsic_value = max(0, trade.strike_price - current_stock_price)
                
                time_value = trade.entry_price * 0.3
                current_option_price = intrinsic_value + time_value
                
                pnl = (current_option_price - trade.entry_price) * trade.quantity * 100
                total_pnl += pnl
                
                enhanced_trades.append({
                    'trade': trade,
                    'current_stock_price': current_stock_price,
                    'current_option_price': round(current_option_price, 2),
                    'pnl': round(pnl, 2),
                    'probability': probability
                })
        
        try:
            return render_template('dashboard.html', 
                                 user=user, 
                                 trades=enhanced_trades, 
                                 total_pnl=total_pnl,
                                 open_trades=open_trades,
                                 market_status=market_status,
                                 top_movers=top_movers)
        except Exception as e:
            logger.error(f"Error rendering dashboard.html: {e}")
            return f"""
            <!DOCTYPE html>
            <html><head><title>Dashboard - ShadowStrike Options</title></head>
            <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; padding: 50px;">
            <h1 style="color: #10b981;">🎯 ShadowStrike Options - Dashboard</h1>
            <p>Welcome {user.username}! ({user.subscription_status} - {user.days_left_in_trial() if user.subscription_status == 'trial' else 'Active'})</p>
            
            {'<div style="background: rgba(239, 68, 68, 0.2); padding: 15px; border-radius: 10px; margin: 20px 0;"><strong>⏰ Trial expires in ' + str(user.days_left_in_trial()) + ' days!</strong> <a href="/subscribe" style="color: #10b981;">Subscribe now</a></div>' if user.subscription_status == 'trial' and user.days_left_in_trial() <= 7 else ''}
            
            <p>Market Status: {market_status['status']}</p>
            <p>Portfolio P&L: ${total_pnl:.2f}</p>
            <p>Open Trades: {open_trades}</p>
            
            <h3>Top Market Movers:</h3>
            {''.join([f"<p>{mover['symbol']}: ${mover['price']} ({mover['change_percent']:+.2f}%)</p>" for mover in top_movers])}
            
            <p><a href="/logout" style="color: #ef4444;">Logout</a> | 
            <a href="/subscribe" style="color: #10b981;">Subscribe</a> | 
            <a href="/mobile-demo" style="color: #10b981;">Mobile App</a></p>
            </body></html>
            """
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return redirect(url_for('login'))

@app.route('/subscribe')
def subscribe():
    if 'user_id' not in session:
        flash('Please login to subscribe', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('login'))
    
    if user.subscription_status == 'active':
        flash('You already have an active subscription!', 'info')
        return redirect(url_for('dashboard'))
    
    return f"""
    <!DOCTYPE html>
    <html><head><title>Subscribe - ShadowStrike Options</title></head>
    <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; padding: 50px;">
    <div style="max-width: 600px; margin: 0 auto; background: rgba(6, 95, 70, 0.3); padding: 40px; border-radius: 15px; text-align: center;">
        <h1 style="color: #10b981;">💳 Continue Your Trading Success</h1>
        <p style="font-size: 1.2em; margin: 20px 0;">Don't lose access to profitable trading opportunities!</p>
        
        <div style="background: rgba(239, 68, 68, 0.2); padding: 20px; border-radius: 10px; margin: 30px 0;">
            <h2 style="color: #ef4444;">⏰ {user.days_left_in_trial()} Days Left in Trial</h2>
        </div>
        
        <div style="font-size: 3em; color: #10b981; margin: 30px 0; font-weight: bold;">$49/month</div>
        <p style="color: #a7f3d0; margin-bottom: 30px;">Cancel anytime • No long-term contracts</p>
        
        <div style="background: rgba(16, 185, 129, 0.1); padding: 25px; border-radius: 10px; margin: 30px 0; text-align: left;">
            <h3 style="color: #10b981; text-align: center; margin-bottom: 20px;">What You Keep:</h3>
            <ul style="color: #a7f3d0; font-size: 1.1em; line-height: 1.8;">
                <li>📊 Real-time options analysis with live market data</li>
                <li>🎯 Advanced options scanner for high-probability trades</li>
                <li>📈 Portfolio tracking with live P&L calculations</li>
                <li>📧 Daily trading alerts and opportunities</li>
                <li>📱 Mobile app access for trading on-the-go</li>
                <li>🤖 AI-powered probability calculations</li>
                <li>💡 Expert trading insights and analysis</li>
            </ul>
        </div>
        
        <div style="margin: 40px 0;">
            <h3 style="color: #10b981; margin-bottom: 20px;">Choose Your Payment Method:</h3>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 30px 0;">
                <button onclick="alert('Stripe payment demo - In production, this would process your card')" 
                        style="background: #6772e5; color: white; padding: 20px; border: none; border-radius: 10px; font-size: 1.1em; font-weight: bold; cursor: pointer;">
                    💳 Pay with Card<br><small style="opacity: 0.8;">Visa, Mastercard, Amex</small>
                </button>
                
                <button onclick="alert('PayPal payment demo - In production, this would redirect to PayPal')" 
                        style="background: #0070ba; color: white; padding: 20px; border: none; border-radius: 10px; font-size: 1.1em; font-weight: bold; cursor: pointer;">
                    🟡 PayPal<br><small style="opacity: 0.8;">PayPal & PayPal Credit</small>
                </button>
            </div>
            
            <p style="color: #a7f3d0; font-size: 0.9em; margin-top: 20px;">
                🔒 Secure payment processing • Your trial continues until {user.trial_end_date.strftime('%B %d, %Y')}
            </p>
        </div>
        
        <div style="margin-top: 30px;">
            <a href="/dashboard" style="color: #a7f3d0; text-decoration: none;">← Continue Trial ({user.days_left_in_trial()} days left)</a>
        </div>
    </div>
    </body></html>
    """

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/mobile-demo')
def mobile_demo():
    return render_template('mobile_demo.html')

@app.route('/market-data')
def market_data():
    market_status = get_market_status()
    top_movers = get_top_movers()
    
    return f"""
    <!DOCTYPE html>
    <html><head><title>Market Data - ShadowStrike Options</title></head>
    <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; padding: 50px;">
    <h1 style="color: #10b981;">📊 Live Market Data</h1>
    <p>Market Status: <strong>{market_status['status']}</strong></p>
    <p>Next Open: {market_status['next_open']}</p>
    
    <h2 style="color: #10b981;">Top Market Movers</h2>
    <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
        <tr style="background: rgba(16, 185, 129, 0.3);">
            <th style="padding: 10px; text-align: left;">Symbol</th>
            <th style="padding: 10px; text-align: left;">Price</th>
            <th style="padding: 10px; text-align: left;">Change</th>
            <th style="padding: 10px; text-align: left;">% Change</th>
        </tr>
        {''.join([f'''
        <tr style="background: rgba(6, 95, 70, 0.3);">
            <td style="padding: 10px; font-weight: bold;">{mover['symbol']}</td>
            <td style="padding: 10px;">${mover['price']}</td>
            <td style="padding: 10px; color: {'#10b981' if mover['change'] >= 0 else '#ef4444'};">{mover['change']:+.2f}</td>
            <td style="padding: 10px; color: {'#10b981' if mover['change_percent'] >= 0 else '#ef4444'};">{mover['change_percent']:+.2f}%</td>
        </tr>
        ''' for mover in top_movers])}
    </table>
    
    <p><a href="/" style="color: #10b981;">Home</a> | <a href="/login" style="color: #10b981;">Login</a></p>
    </body></html>
    """

@app.route('/status')
def status():
    try:
        total_users = User.query.count()
        total_trades = Trade.query.count()
        trial_users = User.query.filter_by(subscription_status='trial').count()
        active_users = User.query.filter_by(subscription_status='active').count()
        db_status = "Connected"
    except Exception as e:
        logger.error(f"Database error in status: {e}")
        total_users = 0
        total_trades = 0
        trial_users = 0
        active_users = 0
        db_status = "Not Connected"
    
    return f"""
    <!DOCTYPE html>
    <html><head><title>Status - ShadowStrike Options</title></head>
    <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
    <h1 style="color: #10b981;">🎯 ShadowStrike Options - System Status</h1>
    <p>Platform Status: ✅ LIVE</p>
    <p>Database Status: {db_status}</p>
    <p>Total Users: {total_users}</p>
    <p>Trial Users: {trial_users}</p>
    <p>Paid Users: {active_users}</p>
    <p>Total Trades: {total_trades}</p>
    <br>
    <a href="/" style="color: #10b981;">Home</a> | 
    <a href="/init-db" style="color: #10b981;">Initialize Database</a>
    </body></html>
    """

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
