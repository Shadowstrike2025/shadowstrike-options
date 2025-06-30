import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import logging
import yfinance as yf
import requests

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

# Market Data Functions
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
        # Simple market hours check (9:30 AM - 4:00 PM ET, Mon-Fri)
        now = datetime.now()
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
        
        is_weekday = now.weekday() < 5  # Monday = 0, Friday = 4
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
    symbols = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX']
    movers = []
    
    for symbol in symbols:
        try:
            data = get_stock_price(symbol)
            if data['price'] > 0:
                movers.append(data)
        except:
            continue
    
    # Sort by absolute change percentage
    movers.sort(key=lambda x: abs(x['change_percent']), reverse=True)
    return movers[:5]  # Top 5 movers

def calculate_option_probability(stock_price, strike_price, days_to_expiry, option_type='CALL'):
    """Simple probability calculation for options"""
    try:
        if days_to_expiry <= 0:
            return 0
        
        # Simple probability model (not Black-Scholes, but good enough for demo)
        price_ratio = stock_price / strike_price
        time_factor = days_to_expiry / 365
        
        if option_type == 'CALL':
            # Call probability increases as stock price > strike price
            if price_ratio >= 1:
                base_prob = 60 + (price_ratio - 1) * 30
            else:
                base_prob = 40 * price_ratio
        else:  # PUT
            # Put probability increases as stock price < strike price
            if price_ratio <= 1:
                base_prob = 60 + (1 - price_ratio) * 30
            else:
                base_prob = 40 / price_ratio
        
        # Adjust for time
        time_adjusted = base_prob * (1 + time_factor * 0.5)
        
        return min(95, max(5, round(time_adjusted, 1)))
    except:
        return 50  # Default probability

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
            
            # Add some demo trades for the demo user
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
        <p>Elite Trading Platform with Live Market Data</p>
        <p><a href="/init-db" style="color: #10b981;">Initialize Database</a> | 
        <a href="/login" style="color: #10b981;">Login</a> | 
        <a href="/register" style="color: #10b981;">Register</a> | 
        <a href="/market-data" style="color: #10b981;">Market Data</a></p>
        </body></html>
        """

@app.route('/init-db')
def initialize_database():
    success = init_database()
    if success:
        return """
        <html><body style="background: linear-gradient(135deg, #1f2937 0%, #065f46 100%); color: white; font-family: Arial; text-align: center; padding: 50px;">
        <h1>✅ Database Initialized!</h1>
        <p>ShadowStrike Options database is ready with demo data!</p>
        <p><strong>Test Accounts Created:</strong></p>
        <p>Username: admin | Password: admin123</p>
        <p>Username: demo | Password: demo123 (has sample trades)</p>
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
            <p>Market Status: {market_status['status']}</p>
            <p>Portfolio P&L: ${total_pnl:.2f}</p>
            <p>Open Trades: {open_trades}</p>
            
            <h3>Top Market Movers:</h3>
            {''.join([f"<p>{mover['symbol']}: ${mover['price']} ({mover['change_percent']:+.2f}%)</p>" for mover in top_movers])}
            
            <p><a href="/logout" style="color: #ef4444;">Logout</a> | <a href="/market-data" style="color: #10b981;">Market Data</a></p>
            </body></html>
            """
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        return redirect(url_for('login'))

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

# API Routes
