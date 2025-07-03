import React from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { View, Text, StyleSheet, TouchableOpacity, Alert, ScrollView, TextInput, Modal, Picker } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { StatusBar } from 'expo-status-bar';

const Tab = createBottomTabNavigator();
const API_URL = "https://shadowstrike-options-2025.onrender.com";

// Login Screen
function LoginScreen({ navigation }) {
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [error, setError] = React.useState('');

  const handleLogin = async () => {
    try {
      const response = await fetch(`${API_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        navigation.replace('Main');
      }
    } catch {
      setError('Login failed');
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>ShadowStrike Login</Text>
      <TextInput
        style={styles.searchInput}
        value={email}
        onChangeText={setEmail}
        placeholder="Email"
        placeholderTextColor="#a7f3d0"
        autoCapitalize="none"
      />
      <TextInput
        style={styles.searchInput}
        value={password}
        onChangeText={setPassword}
        placeholder="Password"
        placeholderTextColor="#a7f3d0"
        secureTextEntry
      />
      <TouchableOpacity style={styles.button} onPress={handleLogin}>
        <Text style={styles.buttonText}>Login</Text>
      </TouchableOpacity>
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
      <TouchableOpacity onPress={() => navigation.navigate('ResetPassword')}>
        <Text style={styles.linkText}>Forgot Password?</Text>
      </TouchableOpacity>
      <TouchableOpacity onPress={() => navigation.navigate('Register')}>
        <Text style={styles.linkText}>Register</Text>
      </TouchableOpacity>
    </View>
  );
}

// Register Screen
function RegisterScreen({ navigation }) {
  const [email, setEmail] = React.useState('');
  const [password, setPassword] = React.useState('');
  const [username, setUsername] = React.useState('');
  const [color, setColor] = React.useState('#10b981');
  const [error, setError] = React.useState('');

  const handleRegister = async () => {
    try {
      const response = await fetch(`${API_URL}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, username, color })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        navigation.replace('Main');
      }
    } catch {
      setError('Registration failed');
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>ShadowStrike Register</Text>
      <TextInput
        style={styles.searchInput}
        value={username}
        onChangeText={setUsername}
        placeholder="Username"
        placeholderTextColor="#a7f3d0"
      />
      <TextInput
        style={styles.searchInput}
        value={email}
        onChangeText={setEmail}
        placeholder="Email"
        placeholderTextColor="#a7f3d0"
        autoCapitalize="none"
      />
      <TextInput
        style={styles.searchInput}
        value={password}
        onChangeText={setPassword}
        placeholder="Password"
        placeholderTextColor="#a7f3d0"
        secureTextEntry
      />
      <TextInput
        style={styles.searchInput}
        value={color}
        onChangeText={setColor}
        placeholder="Theme Color (e.g., #10b981)"
        placeholderTextColor="#a7f3d0"
      />
      <TouchableOpacity style={styles.button} onPress={handleRegister}>
        <Text style={styles.buttonText}>Register</Text>
      </TouchableOpacity>
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
    </View>
  );
}

// Reset Password Screen
function ResetPasswordScreen({ navigation }) {
  const [email, setEmail] = React.useState('');
  const [error, setError] = React.useState('');

  const handleReset = async () => {
    try {
      const response = await fetch(`${API_URL}/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });
      const data = await response.json();
      if (data.error) {
        setError(data.error);
      } else {
        Alert.alert('Success', 'Password reset email sent');
        navigation.navigate('Login');
      }
    } catch {
      setError('Reset failed');
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Reset Password</Text>
      <TextInput
        style={styles.searchInput}
        value={email}
        onChangeText={setEmail}
        placeholder="Email"
        placeholderTextColor="#a7f3d0"
        autoCapitalize="none"
      />
      <TouchableOpacity style={styles.button} onPress={handleReset}>
        <Text style={styles.buttonText}>Send Reset Email</Text>
      </TouchableOpacity>
      {error ? <Text style={styles.errorText}>{error}</Text> : null}
      <TouchableOpacity onPress={() => navigation.navigate('Login')}>
        <Text style={styles.linkText}>Back to Login</Text>
      </TouchableOpacity>
    </View>
  );
}

// Top 10 Screen
function Top10Screen() {
  const [topPicks, setTopPicks] = React.useState([]);
  const [loading, setLoading] = React.useState(false);

  const fetchTopPicks = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/top10`);
      const data = await response.json();
      setTopPicks(data);
    } catch {
      Alert.alert('Error', 'Failed to fetch top picks');
    }
    setLoading(false);
  };

  React.useEffect(() => {
    fetchTopPicks();
  }, []);

  const addToPortfolio = (pick) => {
    Alert.prompt(
      'Add to Portfolio',
      'Enter number of contracts',
      async (contracts) => {
        const analysis = await (await fetch(`${API_URL}/api/scanner?symbol=${pick.symbol}`)).json();
        const trade = {
          symbol: pick.symbol,
          type: pick.type,
          strike: pick.strike || pick.buy_strike,
          price: pick.price,
          contracts: parseInt(contracts),
          stop_loss: analysis[0]?.details?.StopLoss || (pick.strike || pick.buy_strike) * 0.9,
          target_price: (pick.strike || pick.buy_strike) * 1.1
        };
        await fetch(`${API_URL}/api/portfolio`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(trade)
        });
        Alert.alert('Success', 'Trade added to portfolio');
      }
    );
  };

  return (
    <ScrollView style={styles.scrollContainer}>
      <View style={styles.marketContainer}>
        <Text style={styles.title}>🏆 Top 10 Daily Picks</Text>
        {topPicks.map((pick, index) => (
          <TouchableOpacity key={index} style={styles.optionCard} onPress={() => addToPortfolio(pick)}>
            <Text style={styles.optionType}>{pick.symbol} {pick.type} ${pick.strike || pick.buy_strike}</Text>
            <Text style={styles.detailText}>Expiration: {pick.expiration}</Text>
            <Text style={styles.detailText}>Price: ${pick.price?.toFixed(2)}</Text>
            <Text style={styles.detailText}>Probability ITM: {pick.probabilityITM}%</Text>
            {pick.max_profit && (
              <>
                <Text style={styles.detailText}>Max Profit: ${pick.max_profit}</Text>
                <Text style={styles.detailText}>Max Loss: ${pick.max_loss}</Text>
                <Text style={styles.detailText}>Breakeven: ${pick.breakeven}</Text>
              </>
            )}
            <Text style={styles.detailText}>Signals: {pick.signals?.join(', ') || 'None'}</Text>
          </TouchableOpacity>
        ))}
        <TouchableOpacity style={styles.button} onPress={fetchTopPicks} disabled={loading}>
          <Text style={styles.buttonText}>{loading ? 'Loading...' : 'Refresh Picks'}</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

// Scanner Screen
function ScannerScreen() {
  const [scanning, setScanning] = React.useState(false);
  const [searchSymbol, setSearchSymbol] = React.useState('');
  const [showOptionsChain, setShowOptionsChain] = React.useState(false);
  const [optionsData, setOptionsData] = React.useState([]);
  const [selectedStock, setSelectedStock] = React.useState('');

  const runOptionsScanner = async () => {
    setScanning(true);
    try {
      const response = await fetch(`${API_URL}/api/scanner`);
      const data = await response.json();
      setOptionsData(data);
      const message = data.map(item => `${item.symbol} ${item.type} ${item.strike ? '$' + item.strike : ''} - ${item.probabilityITM}%`).join('\n');
      Alert.alert('🎯 High-Probability Options', `Results:\n\n${message}`);
    } catch {
      Alert.alert('Error', 'Failed to run scanner');
    }
    setScanning(false);
  };

  const searchOptionsChain = async () => {
    if (!searchSymbol.trim()) {
      Alert.alert('Enter Symbol', 'Please enter a stock symbol');
      return;
    }
    setSelectedStock(searchSymbol.toUpperCase());
    setScanning(true);
    try {
      const response = await fetch(`${API_URL}/api/scanner?symbol=${searchSymbol.toUpperCase()}`);
      const data = await response.json();
      setOptionsData(data);
      setShowOptionsChain(true);
    } catch {
      Alert.alert('Error', 'Failed to fetch options chain');
    }
    setScanning(false);
  };

  const addToPortfolio = (option) => {
    Alert.prompt(
      'Add to Portfolio',
      'Enter number of contracts',
      async (contracts) => {
        const trade = {
          symbol: selectedStock,
          type: option.type,
          strike: option.strike || option.buy_strike,
          price: option.price,
          contracts: parseInt(contracts),
          stop_loss: option.strike ? option.strike * 0.9 : option.breakeven * 0.9,
          target_price: option.strike ? option.strike * 1.1 : option.breakeven * 1.1
        };
        await fetch(`${API_URL}/api/portfolio`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(trade)
        });
        Alert.alert('Success', 'Trade added to portfolio');
      }
    );
  };

  return (
    <View style={styles.container}>
      <ScrollView style={styles.fullScrollContainer}>
        <Text style={styles.title}>🔍 Options Scanner</Text>
        <Text style={styles.subtitle}>Find High-Probability Trades</Text>
        <View style={styles.scanCard}>
          <Text style={styles.scanTitle}>🎯 Recent Finds</Text>
          {optionsData.map((item, index) => (
            <Text key={index} style={styles.scanItem}>
              {item.symbol} {item.type} {item.strike ? '$' + item.strike : ''} - {item.probabilityITM}% {item.max_profit ? `(Spread: $${item.max_profit})` : ''}
            </Text>
          ))}
        </View>
        <TouchableOpacity style={[styles.button, scanning && styles.buttonDisabled]} onPress={runOptionsScanner} disabled={scanning}>
          <Text style={styles.buttonText}>{scanning ? 'Scanning...' : 'Run Scanner'}</Text>
        </TouchableOpacity>
        <View style={styles.optionsSearchCard}>
          <Text style={styles.scanTitle}>📋 Options Chain Search</Text>
          <TextInput
            style={styles.searchInput}
            value={searchSymbol}
            onChangeText={setSearchSymbol}
            placeholder="Enter symbol (e.g., AAPL)"
            placeholderTextColor="#a7f3d0"
            autoCapitalize="characters"
          />
          <TouchableOpacity style={styles.searchButton} onPress={searchOptionsChain} disabled={scanning}>
            <Text style={styles.searchButtonText}>{scanning ? 'Loading...' : 'Search Options'}</Text>
          </TouchableOpacity>
        </View>
        <Modal visible={showOptionsChain} animationType="slide" presentationStyle="pageSheet">
          <View style={styles.modalContainer}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{selectedStock} Options Chain</Text>
              <TouchableOpacity onPress={() => setShowOptionsChain(false)} style={styles.closeButton}>
                <Text style={styles.closeButtonText}>✕</Text>
              </TouchableOpacity>
            </View>
            <ScrollView style={styles.optionsScrollView}>
              {optionsData.map((option, index) => (
                <View key={index} style={styles.optionCard}>
                  <Text style={[styles.optionType, option.type === 'CALL' ? styles.callType : styles.putType]}>
                    {option.type} {option.strike ? '$' + option.strike : ''}
                  </Text>
                  <Text style={styles.detailText}>Expiration: {option.expiration}</Text>
                  <Text style={styles.detailText}>Price: ${option.price?.toFixed(2)}</Text>
                  <Text style={styles.detailText}>Probability ITM: {option.probabilityITM}%</Text>
                  {option.max_profit && (
                    <>
                      <Text style={styles.detailText}>Max Profit: ${option.max_profit}</Text>
                      <Text style={styles.detailText}>Max Loss: ${option.max_loss}</Text>
                      <Text style={styles.detailText}>Breakeven: ${option.breakeven}</Text>
                    </>
                  )}
                  <TouchableOpacity style={styles.tradeButton} onPress={() => addToPortfolio(option)}>
                    <Text style={styles.tradeButtonText}>Add to Portfolio</Text>
                  </TouchableOpacity>
                </View>
              ))}
            </ScrollView>
          </View>
        </Modal>
      </ScrollView>
    </View>
  );
}

// Trades Screen
function TradesScreen() {
  const [portfolio, setPortfolio] = React.useState([]);
  const [loading, setLoading] = React.useState(false);

  const fetchPortfolio = async () => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/api/portfolio`);
      const data = await response.json();
      setPortfolio(data);
    } catch {
      Alert.alert('Error', 'Failed to fetch portfolio');
    }
    setLoading(false);
  };

  React.useEffect(() => {
    fetchPortfolio();
  }, []);

  return (
    <ScrollView style={styles.scrollContainer}>
      <View style={styles.marketContainer}>
        <Text style={styles.title}>📊 Portfolio</Text>
        {portfolio.map((trade, index) => (
          <View key={index} style={styles.optionCard}>
            <Text style={styles.optionType}>{trade.symbol} {trade.type} ${trade.strike}</Text>
            <Text style={styles.detailText}>Entry: ${trade.entry_price.toFixed(2)}</Text>
            <Text style={styles.detailText}>Current: ${trade.current_price.toFixed(2)}</Text>
            <Text style={[styles.detailText, trade.pnl >= 0 ? styles.positive : styles.negative]}>
              P&L: ${trade.pnl.toFixed(2)}
            </Text>
            <Text style={styles.detailText}>Contracts: {trade.contracts}</Text>
            <Text style={styles.detailText}>Stop Loss: ${trade.stop_loss.toFixed(2)}</Text>
            <Text style={styles.detailText}>Target: ${trade.target_price.toFixed(2)}</Text>
          </View>
        ))}
        <TouchableOpacity style={styles.button} onPress={fetchPortfolio} disabled={loading}>
          <Text style={styles.buttonText}>{loading ? 'Loading...' : 'Refresh Portfolio'}</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

// Market Screen
function MarketScreen() {
  const [stockData, setStockData] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [lastUpdate, setLastUpdate] = React.useState('');
  const [searchSymbol, setSearchSymbol] = React.useState('');
  const [showSearch, setShowSearch] = React.useState(false);

  const fetchMarketData = async (symbols) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_URL}/market-data`);
      const data = await response.json();
      setStockData(data.top_movers);
      setLastUpdate(new Date().toLocaleTimeString());
    } catch {
      Alert.alert('Error', 'Failed to fetch market data');
    }
    setLoading(false);
  };

  React.useEffect(() => {
    fetchMarketData(['SPY', 'QQQ', 'AAPL', 'MSFT', 'TSLA', 'GOOGL', 'AMZN', 'NVDA', 'META', 'NFLX']);
    const interval = setInterval(() => fetchMarketData(['SPY', 'QQQ', 'AAPL', 'MSFT', 'TSLA', 'GOOGL', 'AMZN', 'NVDA', 'META', 'NFLX']), 30000);
    return () => clearInterval(interval);
  }, []);

  const searchStock = async () => {
    if (!searchSymbol.trim()) {
      Alert.alert('Enter Symbol', 'Please enter a stock symbol');
      return;
    }
    await fetchMarketData([searchSymbol.toUpperCase()]);
    setSearchSymbol('');
    setShowSearch(false);
  };

  const getMarketStatus = () => {
    const now = new Date();
    const hour = now.getHours();
    const day = now.getDay();
    const minute = now.getMinutes();
    const isWeekday = day >= 1 && day <= 5;
    const currentMinutes = hour * 60 + minute;
    const marketOpen = 9 * 60 + 30;
    const marketClose = 16 * 60;
    return isWeekday && currentMinutes >= marketOpen && currentMinutes < marketClose ? 'OPEN' : 'CLOSED';
  };

  return (
    <ScrollView style={styles.scrollContainer}>
      <View style={styles.marketContainer}>
        <Text style={styles.title}>📈 Live Market Data</Text>
        <View style={[styles.statusCard, getMarketStatus() === 'OPEN' ? styles.openStatus : styles.closedStatus]}>
          <Text style={styles.statusText}>Market: {getMarketStatus()}</Text>
          <Text style={styles.statusSubtext}>
            {getMarketStatus() === 'OPEN' ? 'Live prices updating' : 'Showing last close prices'}
          </Text>
        </View>
        <View style={styles.searchContainer}>
          <TouchableOpacity style={styles.searchToggle} onPress={() => setShowSearch(!showSearch)}>
            <Text style={styles.searchToggleText}>{showSearch ? 'Close Search' : 'Search Stock'}</Text>
          </TouchableOpacity>
          {showSearch && (
            <View style={styles.searchInputContainer}>
              <TextInput
                style={styles.searchInput}
                value={searchSymbol}
                onChangeText={setSearchSymbol}
                placeholder="Enter symbol (e.g., NVDA)"
                placeholderTextColor="#a7f3d0"
                autoCapitalize="characters"
              />
              <TouchableOpacity style={styles.searchButton} onPress={searchStock}>
                <Text style={styles.searchButtonText}>Search</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>
        {lastUpdate ? <Text style={styles.updateText}>Last Update: {lastUpdate}</Text> : null}
        {stockData.map((stock, index) => (
          <TouchableOpacity
            key={index}
            style={styles.enhancedStockCard}
            onPress={() => {
              Alert.alert(
                `${stock.symbol} Details`,
                `Price: $${stock.price.toFixed(2)}\nChange: ${stock.change >= 0 ? '+' : ''}$${stock.change.toFixed(2)} (${stock.change_percent.toFixed(2)}%)\nVolume: ${stock.volume.toLocaleString()}\nMarket Cap: $${(stock.market_cap / 1e9).toFixed(2)}B`
              );
            }}
          >
            <View style={styles.stockMainRow}>
              <View style={styles.stockLeft}>
                <Text style={styles.stockSymbol}>{stock.symbol}</Text>
                <Text style={styles.stockPrice}>${stock.price.toFixed(2)}</Text>
              </View>
              <View style={styles.stockRight}>
                <Text style={[styles.changeText, stock.change >= 0 ? styles.positive : styles.negative]}>
                  {stock.change >= 0 ? '+' : ''}${Math.abs(stock.change).toFixed(2)}
                </Text>
                <Text style={[styles.percentText, stock.change_percent >= 0 ? styles.positive : styles.negative]}>
                  ({stock.change_percent >= 0 ? '+' : ''}{stock.change_percent.toFixed(2)}%)
                </Text>
              </View>
            </View>
          </TouchableOpacity>
        ))}
        <TouchableOpacity style={[styles.button, loading && styles.buttonDisabled]} onPress={() => fetchMarketData(['SPY', 'QQQ', 'AAPL', 'MSFT', 'TSLA', 'GOOGL', 'AMZN', 'NVDA', 'META', 'NFLX'])} disabled={loading}>
          <Text style={styles.buttonText}>{loading ? 'Loading...' : 'Refresh Data'}</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

// Settings Screen
function SettingsScreen() {
  const [color, setColor] = React.useState('#10b981');
  const [broker, setBroker] = React.useState('');
  const brokers = ['Schwab', 'Fidelity', 'Robinhood', 'TradingView', 'Vanguard', 'Tastytrade', 'Webull', 'TradeStation', 'E-Trade'];

  const updateColor = async () => {
    try {
      await fetch(`${API_URL}/api/update-color`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON
