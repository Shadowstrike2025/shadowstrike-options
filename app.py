import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import logging
import yfinance as yf
import requests
from flask_mail import Mail, Message
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading

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

# Fix for Heroku/Render Postgres URL
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://')

# Initialize extensions
db = SQLAlchemy(app)
mail = Mail(app)

# User Model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subscription_status = db.Column(db.String(20), default='trial')
    trial_end_date = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=30))
    
    # Email Alert Preferences
    email_alerts_enabled = db.Column(db.Boolean, default=True)
    daily_picks_email = db.Column(db.Boolean, default=True)
    portfolio_alerts = db.Column(db.Boolean, default=True)
    market_alerts = db.Column(db.Boolean, default=True)
    email_verified = db.Column(db.Boolean, default=False)

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

# Email Alert Model
class EmailAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    alert_type = db.Column(db.String(50), nullable=False)  # daily_picks, portfolio_update, market_alert
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    subject = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=True)
    
    user = db.relationship('User', backref='email_alerts')

# Email Functions
def send_email_async(app, msg):
    """Send email in background thread"""
    with app.app_context():
        try:
            mail.send(msg)
            logger.info(f"Email sent successfully to {msg.recipients}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")

def send_welcome_email(user_email, username):
    """Send welcome email to new users"""
    try:
        msg = Message(
            subject="🎯 Welcome to ShadowStrike Options!",
            recipients=[user_email],
            html=f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; background: #1f2937; color: white; margin: 0; padding: 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #065f46, #10b981); padding: 30px; border-radius: 15px; }}
                    .header {{ text-align: center; margin-bottom: 30px; }}
                    .content {{ background: rgba(6, 95, 70, 0.3); padding: 25px; border-radius: 10px; margin-bottom: 20px; }}
                    .button {{ background: #10b981; color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: bold; }}
                    .footer {{ text-align: center; font-size: 0.9em; color: #a7f3d0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🎯 Welcome to ShadowStrike Options!</h1>
                        <p>Elite Trading Intelligence Platform</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hello {username}!</h2>
                        <p>Welcome to the future of options trading! Your account has been successfully created and your <strong>30-day free trial</strong> has begun.</p>
                        
                        <h3>🚀 What You Get:</h3>
                        <ul>
                            <li>📊 Real-time market data and analysis</li>
                            <li>🎯 Advanced options scanner</li>
                            <li>📈 Portfolio tracking with live P&L</li>
                            <li>📧 Daily trading alerts and opportunities</li>
                            <li>🤖 AI-powered probability calculations</li>
                        </ul>
                        
                        <p style="text-align: center; margin: 25px 0;">
                            <a href="https://shadowstrike-options-2025.onrender.com/login" class="button">Access Your Dashboard</a>
                        </p>
                    </div>
                    
                    <div class="footer">
                        <p>Start exploring your dashboard and discover profitable trading opportunities!</p>
                        <p><small>This is an automated message from ShadowStrike Options Platform</small></p>
                    </div>
                </div>
            </body>
            </html>
            """
        )
        
        # Send in background thread
        thread = threading.Thread(target=send_email_async, args=(app, msg))
        thread.start()
        
        return True
    except Exception as e:
        logger.error(f"Error sending welcome email: {e}")
        return False

def send_daily_picks_email(user_email, username, picks):
    """Send daily top picks email"""
    try:
        picks_html = ""
        for pick in picks:
            picks_html += f"""
            <tr style="background: rgba(16, 185, 129, 0.1);">
                <td style="padding: 10px; font-weight: bold;">{pick['symbol']}</td>
                <td style="padding: 10px;"><span style="background: {'#10b981' if pick['type'] == 'CALL' else '#ef4444'}; color: white; padding: 3px 8px; border-radius: 4px;">{pick['type']}</span></td>
                <td style="padding: 10px;">${pick['strike']}</td>
                <td style="padding: 10px; font-weight: bold; color: #10b981;">{pick['probability']}%</td>
                <td style="padding: 10px;">${pick['premium']}</td>
            </tr>
            """
        
        msg = Message(
            subject=f"🎯 Daily Options Picks - {datetime.now().strftime('%B %d, %Y')}",
            recipients=[user_email],
            html=f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; background: #1f2937; color: white; margin: 0; padding: 20px; }}
                    .container {{ max-width: 700px; margin: 0 auto; background: linear-gradient(135deg, #065f46, #10b981); padding: 30px; border-radius: 15px; }}
                    .header {{ text-align: center; margin-bottom: 25px; }}
                    .content {{ background: rgba(6, 95, 70, 0.3); padding: 25px; border-radius: 10px; margin-bottom: 20px; }}
                    .picks-table {{ width: 100%; border-collapse: collapse; background: rgba(16, 185, 129, 0.2); border-radius: 8px; overflow: hidden; }}
                    .picks-table th {{ background: rgba(16, 185, 129, 0.4); padding: 12px; text-align: left; color: #a7f3d0; }}
                    .button {{ background: #10b981; color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: bold; }}
                    .footer {{ text-align: center; font-size: 0.9em; color: #a7f3d0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>🎯 Today's Top Options Picks</h1>
                        <p>{datetime.now().strftime('%A, %B %d, %Y')}</p>
                    </div>
                    
                    <div class="content">
                        <h2>Hello {username}!</h2>
                        <p>Here are today's highest probability options trades identified by our AI analysis:</p>
                        
                        <table class="picks-table">
                            <thead>
                                <tr>
                                    <th>Symbol</th>
                                    <th>Type</th>
                                    <th>Strike</th>
                                    <th>Probability</th>
                                    <th>Premium</th>
                                </tr>
                            </thead>
                            <tbody>
                                {picks_html}
                            </tbody>
                        </table>
                        
                        <p style="margin-top: 20px;"><strong>⚠️ Disclaimer:</strong> These are educational analysis results only. Always conduct your own research and consult with licensed financial advisors before making trading decisions.</p>
                        
                        <p style="text-align: center; margin: 25px 0;">
                            <a href="https://shadowstrike-options-2025.onrender.com/dashboard" class="button">View Full Analysis</a>
                        </p>
                    </div>
                    
                    <div class="footer">
                        <p>Happy Trading!</p>
                        <p><small>To manage your email preferences, visit your dashboard settings.</small></p>
                    </div>
                </div>
            </body>
            </html>
            """
        )
        
        # Send in background thread
        thread = threading.Thread(target=send_email_async, args=(app, msg))
        thread.start()
        
        return True
    except Exception as e:
        logger.error(f"Error sending daily picks email: {e}")
        return False

def send_portfolio_alert(user_email, username, alert_message, pnl_change):
    """Send portfolio alert email"""
    try:
        msg = Message(
            subject=f"📊 Portfolio Alert - ShadowStrike Options",
            recipients=[user_email],
            html=f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; background: #1f2937; color: white; margin: 0; padding: 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #065f46, #10b981); padding: 30px; border-radius: 15px; }}
                    .header {{ text-align: center; margin-bottom: 25px; }}
                    .alert {{ background: {'rgba(16, 185, 129, 0.2)' if pnl_change >= 0 else 'rgba(239, 68, 68, 0.2)'}; border: 1px solid {'#10b981' if pnl_change >= 0 else '#ef4444'}; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                    .button {{ background: #10b981; color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: bold; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>📊 Portfolio Alert</h1>
                    </div>
                    
                    <p>Hello {username},</p>
                    
                    <div class="alert">
                        <h3>{'🎉' if pnl_change >= 0 else '⚠️'} {alert_message}</h3>
                        <p style="font-size: 1.2em; font-weight: bold; color: {'#10b981' if pnl_change >= 0 else '#ef4444'};">
                            Portfolio Change: {'$' if pnl_change >= 0 else '-$'}{abs(pnl_change):,.2f}
                        </p>
                    </div>
                    
                    <p style="text-align: center;">
                        <a href="https://shadowstrike-options-2025.onrender.com/dashboard" class="button">View Portfolio</a>
                    </p>
                </div>
            </body>
            </html>
            """
        )
        
        # Send in background thread
        thread = threading.Thread(target=send_email_async, args=(app, msg))
        thread.start()
        
        return True
    except Exception as e:
        logger.error(f"Error sending portfolio alert: {e}")
        return False

# Market Data Functions (same as before)
def get_stock_price(symbol):
    """Get current stock price using yfinance"""
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
    """Check if market is open"""
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
    """Get top moving stocks"""
    symbols = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL']  # Reduced to avoid rate limits
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
    """Simple probability calculation for options"""
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

def generate_daily_picks():
    """Generate daily top picks for emails"""
    picks = []
    symbols = ['SPY', 'QQQ', 'AAPL']
    
    for symbol in symbols:
        try:
            stock_data = get_stock_price(symbol)
            if stock_data['price'] > 0:
                # Generate call and put options
                for option_type in ['CALL', 'PUT']:
                    strike = stock_data['price'] + (10 if option_type == 'CALL' else -10)
                    probability = calculate_option_probability(stock_data['price'], strike, 30, option_type)
                    premium = round(2 + (probability / 100) * 8, 2)  # Estimate premium
                    
                    if probability >= 65:  # Only high probability trades
                        picks.append({
                            'symbol': symbol,
                            'type': option_type,
                            'strike': int(strike),
                            'probability': probability,
                            'premium': premium
                        })
        except:
            continue
    
    return sorted(picks, key=lambda x: x['probability'], reverse=True)[:5]

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
                email_verified=True
            )
            db.session.add(admin)
            
            # Create demo user
            demo = User(
                username='demo',
                email='demo@shadowstrike.com',
                password_hash=generate_password_hash('demo123'),
                email_verified=True
            )
            db.session.add(demo)
            
            # Add some demo trades
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
            logger.info("Database initialized successfully with demo data!")
            return True
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        return False

# Routes (keeping existing routes, adding new email routes)
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
        <p>Elite Trading Platform with Email Alerts</p>
        <p><a href="/init-db" style="color: #10b981;">Initialize Database</a> | 
        <a href="/login" style="color: #10b981;">Login</a> | 
        <a href="/register" style="color: #10b981;">Register</a> | 
        <a href="/test-email" style="color: #10b981;">Test Email</a></p>
        </body></html>
        """

@app.route('/init-db')
def initialize_database():
    success = init_database()
    if success:
        return """
        <html><body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
        <h1>✅ Database Initialized!</h1>
        <p>ShadowStrike Options database is ready with email alerts!</p>
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

# New Email Routes
@app.route('/test-email')
def test_email():
    """Test email functionality"""
    try:
        # Generate test picks
        picks = generate_daily_picks()
        
        # Send test email
        success = send_daily_picks_email('demo@shadowstrike.com', 'Demo User', picks)
        
        if success:
            return """
            <html><body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
            <h1>📧 Test Email Sent!</h1>
            <p>Check your email inbox for the daily picks email.</p>
            <a href="/" style="color: #10b981;">Back to Home</a>
            </body></html>
            """
        else:
            return """
            <html><body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
            <h1>❌ Email Test Failed</h1>
            <p>Check the logs for error details</p>
            <a href="/" style="color: #10b981;">Back to Home</a>
            </body></html>
            """
    except Exception as e:
        logger.error(f"Test email error: {e}")
        return f"Error: {e}"

@app.route('/send-daily-picks')
def send_daily_picks():
    """Send daily picks to all subscribed users"""
    try:
        picks = generate_daily_picks()
        users = User.query.filter_by(daily_picks_email=True, email_verified=True).all()
        
        sent_count = 0
        for user in users:
            if send_daily_picks_email(user.email, user.username, picks):
                sent_count += 1
                
                # Log the email
                alert = EmailAlert(
                    user_id=user.id,
                    alert_type='daily_picks',
                    subject=f"Daily Options Picks - {datetime.now().strftime('%B %d, %Y')}",
                    content=f"Sent {len(picks)} picks"
                )
                db.session.add(alert)
        
        db.session.commit()
        
        return f"""
        <html><body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
        <h1>📧 Daily Picks Sent!</h1>
        <p>Sent to {sent_count} users</p>
        <p>Picks generated: {len(picks)}</p>
        <a href="/" style="color: #10b981;">Back to Home</a>
        </body></html>
        """
    except Exception as e:
        logger.error(f"Daily picks email error: {e}")
        return f"Error: {e}"

# Keep all existing routes (login, register, dashboard, etc.) - they remain the same
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
            
            # Create new user
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password)
            )
            db.session.add(user)
            db.session.commit()
            
            # Send welcome email
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
            <button type="submit" style="width: 100%; padding: 12px; background: #10b981; color: white; border: none; border-radius: 5px; font-weight: bold;">Register & Get Email Alerts</button>
        </form>
        <p style="text-align: center; margin-top: 20px;">
            <a href="/" style="color: #10b981;">Home</a> | 
            <a href="/login" style="color: #10b981;">Login</a>
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
        
        # Get market data
        market_status = get_market_status()
        top_movers = get_top_movers()
        
        # Get user's trades with real P&L
        trades = Trade.query.filter_by(user_id=user.id).all()
        
        # Calculate portfolio stats with real prices
        total_pnl = 0
        open_trades = 0
        enhanced_trades = []
        
        for trade in trades:
            if trade.status == 'open':
                open_trades += 1
                # Get current stock price
                stock_data = get_stock_price(trade.symbol)
                current_stock_price = stock_data['price']
                
                # Calculate option probability
                days_to_expiry = 30  # Assume 30 days for demo
                probability = calculate_option_probability(
                    current_stock_price, trade.strike_price, days_to_expiry, trade.option_type
                )
                
                # Estimate current option price (simplified)
                if trade.option_type == 'CALL':
                    intrinsic_value = max(0, current_stock_price - trade.strike_price)
                else:
                    intrinsic_value = max(0, trade.strike_price - current_stock_price)
                
                time_value = trade.entry_price * 0.3  # Assume 30% time value remaining
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
            <p>Welcome {user.username}! ({user.subscription_status})</p>
            <p>Email Alerts: {'Enabled' if user.email_alerts_enabled else 'Disabled'}</p>
            <p>Market Status: {market_status['status']}</p>
            <p>Portfolio P&L: ${total_pnl:.2f}</p>
            <p>Open Trades: {open_trades}</p>
            
            <h3>Top Market Movers:</h3>
            {''.join([f"<p>{mover['symbol']}: ${mover['price']} ({mover['change_percent']:+.2f}%)</p>" for mover in top_movers])}
            
            <p><a href="/logout" style="color: #ef4444;">Logout</a> | 
            <a href="/email-settings" style="color: #10b981;">Email Settings</a> | 
            <a href="/market-data" style="color: #10b981;">Market Data</a></p>
            </body></html>
            """
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return redirect(url_for('login'))

@app.route('/email-settings', methods=['GET', 'POST'])
def email_settings():
    """Manage user email preferences"""
    if 'user_id' not in session:
        flash('Please login to access email settings', 'error')
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        try:
            user.email_alerts_enabled = bool(request.form.get('email_alerts_enabled'))
            user.daily_picks_email = bool(request.form.get('daily_picks_email'))
            user.portfolio_alerts = bool(request.form.get('portfolio_alerts'))
            user.market_alerts = bool(request.form.get('market_alerts'))
            
            db.session.commit()
            flash('Email preferences updated successfully!', 'success')
        except Exception as e:
            logger.error(f"Email settings update error: {e}")
            flash('Error updating preferences', 'error')
    
    return f"""
    <!DOCTYPE html>
    <html><head><title>Email Settings - ShadowStrike Options</title></head>
    <body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; padding: 50px;">
    <div style="max-width: 600px; margin: 0 auto; background: rgba(6, 95, 70, 0.3); padding: 30px; border-radius: 15px;">
        <h1 style="color: #10b981; text-align: center;">📧 Email Alert Settings</h1>
        
        <form method="POST">
            <div style="margin: 20px 0;">
                <label style="display: flex; align-items: center; gap: 10px;">
                    <input type="checkbox" name="email_alerts_enabled" {'checked' if user.email_alerts_enabled else ''}>
                    <strong>Enable All Email Alerts</strong>
                </label>
            </div>
            
            <div style="margin: 20px 0;">
                <label style="display: flex; align-items: center; gap: 10px;">
                    <input type="checkbox" name="daily_picks_email" {'checked' if user.daily_picks_email else ''}>
                    Daily Top Picks Email (Morning)
                </label>
            </div>
            
            <div style="margin: 20px 0;">
                <label style="display: flex; align-items: center; gap: 10px;">
                    <input type="checkbox" name="portfolio_alerts" {'checked' if user.portfolio_alerts else ''}>
                    Portfolio Change Alerts
                </label>
            </div>
            
            <div style="margin: 20px 0;">
                <label style="display: flex; align-items: center; gap: 10px;">
                    <input type="checkbox" name="market_alerts" {'checked' if user.market_alerts else ''}>
                    Market Opening/Closing Alerts
                </label>
            </div>
            
            <button type="submit" style="width: 100%; padding: 12px; background: #10b981; color: white; border: none; border-radius: 5px; font-weight: bold; margin-top: 20px;">
                Save Preferences
            </button>
        </form>
        
        <p style="text-align: center; margin-top: 20px;">
            <a href="/dashboard" style="color: #10b981;">Back to Dashboard</a>
        </p>
    </div>
    </body></html>
    """

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/market-data')
def market_data():
    """Standalone market data page"""
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
            <th style="padding: 10px; text-align: left;">Volume</th>
        </tr>
        {''.join([f'''
        <tr style="background: rgba(6, 95, 70, 0.3);">
            <td style="padding: 10px; font-weight: bold;">{mover['symbol']}</td>
            <td style="padding: 10px;">${mover['price']}</td>
            <td style="padding: 10px; color: {'#10b981' if mover['change'] >= 0 else '#ef4444'};">{mover['change']:+.2f}</td>
            <td style="padding: 10px; color: {'#10b981' if mover['change_percent'] >= 0 else '#ef4444'};">{mover['change_percent']:+.2f}%</td>
            <td style="padding: 10px;">{mover['volume']:,}</td>
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
        total_emails = EmailAlert.query.count()
        db_status = "Connected"
    except Exception as e:
        logger.error(f"Database error in status: {e}")
        total_users = 0
        total_trades = 0
        total_emails = 0
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
        <p>Emails Sent: {total_emails}</p>
        <br>
        <a href="/" style="color: #10b981;">Home</a> | 
        <a href="/test-email" style="color: #10b981;">Test Email</a> |
        <a href="/send-daily-picks" style="color: #10b981;">Send Daily Picks</a>
        </body></html>
        """
@app.route('/mobile-demo')
def mobile_demo():
    """Mobile app demo - responsive web version"""
    return render_template('mobile_demo.html')
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
