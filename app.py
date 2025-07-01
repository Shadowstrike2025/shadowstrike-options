
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
import stripe
import paypalrestsdk
import json

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
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_your_stripe_secret_key')
app.config['STRIPE_PUBLIC_KEY'] = os.environ.get('STRIPE_PUBLIC_KEY', 'pk_test_your_stripe_public_key')

# PayPal Configuration
paypalrestsdk.configure({
    "mode": "sandbox",  # sandbox or live
    "client_id": os.environ.get('PAYPAL_CLIENT_ID', 'your_paypal_client_id'),
    "client_secret": os.environ.get('PAYPAL_CLIENT_SECRET', 'your_paypal_client_secret')
})

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
    subscription_status = db.Column(db.String(20), default='trial')  # trial, active, expired, cancelled
    trial_end_date = db.Column(db.DateTime, default=lambda: datetime.utcnow() + timedelta(days=30))
    subscription_start_date = db.Column(db.DateTime, nullable=True)
    subscription_end_date = db.Column(db.DateTime, nullable=True)
    
    # Payment fields
    stripe_customer_id = db.Column(db.String(100), nullable=True)
    stripe_subscription_id = db.Column(db.String(100), nullable=True)
    paypal_subscription_id = db.Column(db.String(100), nullable=True)
    payment_method = db.Column(db.String(20), nullable=True)  # stripe, paypal
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

# Trade Model (same as before)
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
    payment_method = db.Column(db.String(20), nullable=False)  # stripe, paypal
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD')
    status = db.Column(db.String(20), nullable=False)  # pending, completed, failed, refunded
    transaction_date = db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.String(200), nullable=True)
    
    user = db.relationship('User', backref='payment_transactions')

# Email Alert Model (same as before)
class EmailAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    alert_type = db.Column(db.String(50), nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    subject = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=True)
    
    user = db.relationship('User', backref='email_alerts')

# Payment Functions
def create_stripe_customer(user):
    """Create Stripe customer for user"""
    try:
        customer = stripe.Customer.create(
            email=user.email,
            metadata={'user_id': user.id, 'username': user.username}
        )
        user.stripe_customer_id = customer.id
        db.session.commit()
        return customer
    except Exception as e:
        logger.error(f"Error creating Stripe customer: {e}")
        return None

def create_stripe_subscription(user, payment_method_id):
    """Create Stripe subscription for user"""
    try:
        if not user.stripe_customer_id:
            customer = create_stripe_customer(user)
            if not customer:
                return None
        
        # Attach payment method to customer
        stripe.PaymentMethod.attach(
            payment_method_id,
            customer=user.stripe_customer_id,
        )
        
        # Set as default payment method
        stripe.Customer.modify(
            user.stripe_customer_id,
            invoice_settings={'default_payment_method': payment_method_id}
        )
        
        # Create subscription (starts after trial ends)
        subscription = stripe.Subscription.create(
            customer=user.stripe_customer_id,
            items=[{'price': 'price_shadowstrike_monthly'}],  # You'll need to create this in Stripe
            trial_end=int(user.trial_end_date.timestamp()),
            metadata={'user_id': user.id}
        )
        
        user.stripe_subscription_id = subscription.id
        user.payment_method = 'stripe'
        db.session.commit()
        
        return subscription
    except Exception as e:
        logger.error(f"Error creating Stripe subscription: {e}")
        return None

def send_payment_success_email(user, amount, transaction_id):
    """Send payment confirmation email"""
    try:
        msg = Message(
            subject="💳 Payment Confirmation - ShadowStrike Options",
            recipients=[user.email],
            html=f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; background: #1f2937; color: white; margin: 0; padding: 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #065f46, #10b981); padding: 30px; border-radius: 15px; }}
                    .header {{ text-align: center; margin-bottom: 25px; }}
                    .content {{ background: rgba(6, 95, 70, 0.3); padding: 25px; border-radius: 10px; }}
                    .amount {{ font-size: 2em; color: #10b981; font-weight: bold; text-align: center; margin: 20px 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>💳 Payment Confirmed!</h1>
                    </div>
                    
                    <div class="content">
                        <h2>Thank you, {user.username}!</h2>
                        <p>Your payment has been successfully processed.</p>
                        
                        <div class="amount">${amount:.2f}</div>
                        
                        <p><strong>Transaction Details:</strong></p>
                        <ul>
                            <li>Transaction ID: {transaction_id}</li>
                            <li>Date: {datetime.now().strftime('%B %d, %Y')}</li>
                            <li>Service: ShadowStrike Options Monthly Subscription</li>
                            <li>Next Billing: {(datetime.now() + timedelta(days=30)).strftime('%B %d, %Y')}</li>
                        </ul>
                        
                        <p>Your subscription is now active and you have full access to all premium features!</p>
                        
                        <p style="text-align: center; margin-top: 25px;">
                            <a href="https://shadowstrike-options-2025.onrender.com/dashboard" 
                               style="background: #10b981; color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; font-weight: bold;">
                                Access Your Dashboard
                            </a>
                        </p>
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
        logger.error(f"Error sending payment confirmation email: {e}")
        return False

def send_trial_expiry_warning(user, days_left):
    """Send trial expiry warning email"""
    try:
        msg = Message(
            subject=f"⏰ {days_left} Days Left in Your ShadowStrike Trial",
            recipients=[user.email],
            html=f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; background: #1f2937; color: white; margin: 0; padding: 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; background: linear-gradient(135deg, #065f46, #10b981); padding: 30px; border-radius: 15px; }}
                    .urgent {{ background: rgba(239, 68, 68, 0.2); border: 1px solid #ef4444; padding: 20px; border-radius: 10px; margin: 20px 0; }}
                    .button {{ background: #10b981; color: white; padding: 12px 25px; text-decoration: none; border-radius: 8px; display: inline-block; font-weight: bold; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>⏰ Your Trial is Ending Soon!</h1>
                    
                    <div class="urgent">
                        <h3>Only {days_left} days left in your free trial!</h3>
                        <p>Don't lose access to your profitable trading analysis.</p>
                    </div>
                    
                    <p>Hi {user.username},</p>
                    <p>Your 30-day free trial of ShadowStrike Options will expire in {days_left} days.</p>
                    
                    <h3>🎯 What you'll lose access to:</h3>
                    <ul>
                        <li>Real-time options analysis</li>
                        <li>Daily high-probability trade alerts</li>
                        <li>Portfolio tracking with live P&L</li>
                        <li>Advanced options scanner</li>
                        <li>Mobile app access</li>
                    </ul>
                    
                    <p style="text-align: center; margin: 25px 0;">
                        <a href="https://shadowstrike-options-2025.onrender.com/subscribe" class="button">
                            Continue for Only $49/month
                        </a>
                    </p>
                    
                    <p><small>Cancel anytime. No long-term contracts.</small></p>
                </div>
            </body>
            </html>
            """
        )
        
        thread = threading.Thread(target=send_email_async, args=(app, msg))
        thread.start()
        return True
    except Exception as e:
        logger.error(f"Error sending trial warning email: {e}")
        return False

# Keep all existing email functions (send_email_async, send_welcome_email, etc.)
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
                            <li>📱 Mobile app access</li>
                        </ul>
                        
                        <p style="text-align: center; margin: 25px 0;">
                            <a href="https://shadowstrike-options-2025.onrender.com/login" class="button">Access Your Dashboard</a>
                        </p>
                    </div>
                    
                    <div class="footer">
                        <p>Start exploring your dashboard and discover profitable trading opportunities!</p>
                        <p><small>After your 30-day trial, continue for just $49/month. Cancel anytime.</small></p>
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

# Keep all existing market data functions (same as before)
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

def generate_daily_picks():
    picks = []
    symbols = ['SPY', 'QQQ', 'AAPL']
    
    for symbol in symbols:
        try:
            stock_data = get_stock_price(symbol)
            if stock_data['price'] > 0:
                for option_type in ['CALL', 'PUT']:
                    strike = stock_data['price'] + (10 if option_type == 'CALL' else -10)
                    probability = calculate_option_probability(stock_data['price'], strike, 30, option_type)
                    premium = round(2 + (probability / 100) * 8, 2)
                    
                    if probability >= 65:
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

# Access Control Decorator
def subscription_required(f):
    """Decorator to check if user has active subscription"""
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
                subscription_status='active',  # Give admin permanent access
                subscription_start_date=datetime.utcnow(),
                subscription_end_date=datetime.utcnow() + timedelta(days=365)
            )
            db.session.add(admin)
            
            # Create demo user with active trial
            demo = User(
                username='demo',
                email='demo@shadowstrike.com',
                password_hash=generate_password_hash('demo123'),
                email_verified=True,
                subscription_status='trial',
                trial_end_date=datetime.utcnow() + timedelta(days=25)  # 25 days left
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
            logger.info("Database initialized successfully with payment system!")
            return True
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        return False
