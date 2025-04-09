from flask import Flask, render_template, request, redirect, url_for, session, send_file
from io import BytesIO, StringIO
import asyncio
import random
import aiohttp
from aiohttp_socks import ProxyConnector
import os
from dotenv import load_dotenv
import qrcode
import base64

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

API_BASE_URL = os.getenv('API_BASE_URL')
API_KEY = os.getenv('API_KEY')
AFFILIATE_ID = os.getenv('AFFILIATE_ID')

#Donations data (optional, just in honor of eXch)
DONATIONS = [
    {"project": "Tor Project", "amount": "5 ETH", "date": "July 2023", "txid": "0xb8a54c3468328af8782ab7bb313c376d4a89e5a54c2f74db451250f2fdeed461"},
    {"project": "SimpleX Chat", "amount": "3 ETH", "date": "November 2023", "txid": "0x21f0da3982926d693c915b30a8a138db48f469989bff3e9e6434916fa2d3783f"},
    {"project": "Tornado Cash Legal Defense", "amount": "31 ETH", "date": "June 2024", "txid": "0x98bfc604c917ccc83d1a86b7af1542011a5aa54208dd110036e2c280a963a498"},
    {"project": "DivestOS ROM", "amount": "1 BTC", "date": "June 2024", "txid": "782153c2193b2801dfcdb9458ebc4125c033cfbe5ff554741e1857d37c079949"},
    {"project": "SimpleX Chat", "amount": "1 BTC", "date": "June 2024", "txid": "1c72e10a91f06979cd4c8d239ef548c10a1515573187c7f2d9a2229d1b5ffcee"},
    {"project": "Thorchain developers", "amount": "1 BTC", "date": "August 2024", "txid": "e21424bcd1e59735b5d4b43e70b59d1985e148411e6c197112207cd4c4524ea7"},
    {"project": "Bisq Light Client Project", "amount": "0.555 BTC", "date": "January 2025", "txid": "3fcebcf2043abbc4ad60cd0af1b085533ad6f1fe918b892ba408c60524fa367b"},
    {"project": "Bisq Light Client Project", "amount": "0.7 BTC", "date": "March 2025", "txid": "44232a707d69a27d449885f2d920c441980964e119fed61a2585c6913449f972"},
    {"project": "MMGen multicurrency wallet", "amount": "2 BTC", "date": "March 2025", "txid": "b97638e1c0de516e99689034fa303ca205b5dffbd67848beb3f01bf9b3829d59"}
]

def get_random_donation():
    return random.choice(DONATIONS)

async def fetch_api(endpoint, method='GET', data=None):
    """Fetches data from the API using Tor SOCKS proxy."""
    url = f"{API_BASE_URL}/{endpoint}"
    connector = ProxyConnector.from_url('socks5://127.0.0.1:9050') 
    
    
    headers = {
        'X-Requested-With': 'XMLHttpRequest'
    }
    
    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            if method == 'GET':
                async with session.get(url, params=data, headers=headers, ssl=False) as response:
                    if response.status != 200:
                        return {'error': f'API request failed with status {response.status}'}
                    if endpoint == 'order/fetch_guarantee':
                        return await response.text()
                    try:
                        return await response.json()
                    except Exception as e:
                        return {'error': f'API response for {endpoint} is not valid JSON. Status: {response.status}'}
            elif method == 'POST':
                async with session.post(url, data=data, headers=headers, ssl=False) as response:
                    if response.status != 200:
                        return {'error': f'API request failed with status {response.status}'}
                    try:
                        return await response.json()
                    except Exception as e:
                        return {'error': f'API response for {endpoint} is not valid JSON. Status: {response.status}'}
    except Exception as e:
        print(f"API Error: {str(e)}")
        return {'error': str(e)}

def generate_qr_code(address):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(address)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

async def get_dynamic_rates():
    """Fetches dynamic exchange rates and reserves from the API through Tor."""
    result = await fetch_api('rates', data={'rate_mode': 'dynamic'})
    if not isinstance(result, dict) or 'error' in result:
        error_msg = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Invalid response'
        print(f"Error fetching dynamic rates: {error_msg}")
        return {}
    return result

async def get_flat_rates():
    """Fetches flat exchange rates and reserves from the API through Tor."""
    result = await fetch_api('rates', data={'rate_mode': 'flat'})
    if not isinstance(result, dict) or 'error' in result:
        error_msg = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Invalid response'
        print(f"Error fetching flat rates: {error_msg}")
        return {}
    return result

async def get_btc_pools():
    """Fetches BTC pool information from the API."""
    result = await fetch_api('status')
    if not isinstance(result, dict) or 'error' in result:
        error_msg = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Invalid response'
        print(f"Error fetching BTC pools: {error_msg}")
        return {'aggregated_balance': 0.0, 'mixed_balance': 0.0}
    
    agg_balance = result.get('aggregated_balance')
    mix_balance = result.get('mixed_balance')
    if agg_balance is not None and mix_balance is not None:
        try:
            return {
                'aggregated_balance': float(agg_balance),
                'mixed_balance': float(mix_balance)
            }
        except (ValueError, TypeError) as e:
            print(f"Error parsing BTC pools data: {str(e)}")
            return {'aggregated_balance': 0.0, 'mixed_balance': 0.0} 
    else:
        print("Warning: Pool balances not found in response")
        return {'aggregated_balance': 0.0, 'mixed_balance': 0.0} 

@app.route('/', methods=['GET', 'POST'])
async def index():
    results = await asyncio.gather(
        get_dynamic_rates(),
        get_flat_rates(),
        get_btc_pools()
    )
    dynamic_rates_data, flat_rates_data, pools = results

    currencies = set()
    available_pairs = {}
    dynamic_rates = dynamic_rates_data
    flat_rates = flat_rates_data
    reserves = {}
    erc20_currencies = {'USDT', 'USDC', 'DAI'}

    if isinstance(dynamic_rates_data, dict) and 'error' not in dynamic_rates_data:
        for pair, info in dynamic_rates_data.items():
            if '_' not in pair: continue
            from_curr, to_curr = pair.split('_')
            if from_curr != to_curr:
                currencies.add(from_curr)
                currencies.add(to_curr)
                if from_curr not in available_pairs:
                    available_pairs[from_curr] = []
                if to_curr not in available_pairs[from_curr]:
                    available_pairs[from_curr].append(to_curr)
                if 'reserve' in info:
                    reserves[to_curr] = float(info['reserve'])
    else:
        error_msg = dynamic_rates_data.get('error', 'Unknown API error') if isinstance(dynamic_rates_data, dict) else 'Invalid response'
        print(f"API Error processing dynamic rates: {error_msg}")
        dynamic_rates = {}

    if isinstance(flat_rates_data, dict) and 'error' in flat_rates_data:
        print(f"API Error fetching flat rates: {flat_rates_data['error']}")
        flat_rates = {}

    form_data = request.form.to_dict() if request.method == 'POST' else {}
    if not form_data:
        form_data = {'from_currency': 'BTC', 'to_currency': 'ETH', 'rate_mode': 'dynamic'}
    
    from_amount = form_data.get('from_amount', '')
    calculation = None

    filtered_available_pairs = {}
    if form_data and 'from_currency' in form_data:
        from_currency = form_data['from_currency']
        filtered_available_pairs[from_currency] = [curr for curr in available_pairs.get(from_currency, []) if curr != from_currency]
    else:
        filtered_available_pairs = available_pairs

    show_btc_pools = form_data and form_data.get('to_currency') == 'BTC'
    display_pools = pools if show_btc_pools else None

    return render_template('index.html',
                          currencies=sorted(list(currencies)),
                          dynamic_rates=dynamic_rates,
                          flat_rates=flat_rates,
                          pools=display_pools,
                          available_pairs=filtered_available_pairs,
                          form_data=form_data,
                          from_amount=from_amount,
                          max=max,
                          calculation=calculation,
                          erc20_currencies=erc20_currencies,
                          reserves=reserves,
                          donation=None)

@app.route('/create_exchange', methods=['POST'])
async def create_exchange():
    data = {
        'from_currency': request.form['from_currency'],
        'to_currency': request.form['to_currency'],
        'to_address': request.form['to_address'],
        'refund_address': request.form.get('refund_address', ''),
        'rate_mode': request.form['rate_mode'],
        'ref': AFFILIATE_ID,
        'aggregation': request.form.get('aggregation', 'yes') if request.form['to_currency'] == 'BTC' else 'any'
    }
    action = request.form.get('action')
    from_amount = request.form.get('from_amount', '')

    results = await asyncio.gather(
        get_dynamic_rates(),
        get_flat_rates(),
        get_btc_pools() if request.form['to_currency'] == 'BTC' else asyncio.sleep(0)
    )
    dynamic_rates_data, flat_rates_data, pools = results

    currencies = set()
    available_pairs = {}
    reserves = {}
    erc20_currencies = {'USDT', 'USDC', 'DAI'}

    if isinstance(dynamic_rates_data, dict) and 'error' not in dynamic_rates_data:
        for pair, info in dynamic_rates_data.items():
            if '_' not in pair: continue
            from_curr, to_curr = pair.split('_')
            if from_curr != to_curr:
                currencies.add(from_curr)
                currencies.add(to_curr)
                if from_curr not in available_pairs:
                    available_pairs[from_curr] = []
                if to_curr not in available_pairs[from_curr]:
                    available_pairs[from_curr].append(to_curr)
                if 'reserve' in info:
                    reserves[to_curr] = float(info['reserve'])
    elif action == 'calculate':
        error_msg = dynamic_rates_data.get('error', 'API Error') if isinstance(dynamic_rates_data, dict) else 'Invalid API response'
        return render_template('index.html',
                              error=f"Could not load dynamic rates: {error_msg}",
                              currencies=[],
                              dynamic_rates={},
                              flat_rates={},
                              pools=None,
                              available_pairs={},
                              form_data=data,
                              from_amount=from_amount)

    flat_rates = flat_rates_data
    if isinstance(flat_rates_data, dict) and 'error' in flat_rates_data:
        print(f"API Error fetching flat rates: {flat_rates_data['error']}")
        if action == 'calculate' and data.get('rate_mode') == 'flat':
            return render_template('index.html',
                                 error=f"Could not load flat rates: {flat_rates_data['error']}",
                                 currencies=sorted(list(currencies)),
                                 form_data=data,
                                 from_amount=from_amount)
        flat_rates = {}

    show_btc_pools = data['to_currency'] == 'BTC'
    display_pools = pools if show_btc_pools else None

    if action == 'calculate':
        rates_source = flat_rates if data['rate_mode'] == 'flat' else dynamic_rates_data
        if not isinstance(rates_source, dict) or 'error' in rates_source:
            error_msg = rates_source.get('error', 'Failed to load rates') if isinstance(rates_source, dict) else 'Invalid API response'
            return render_template('index.html',
                                 error=f"Error loading {data['rate_mode']} rates: {error_msg}",
                                 currencies=sorted(list(currencies)),
                                 dynamic_rates=dynamic_rates_data if isinstance(dynamic_rates_data, dict) else {},
                                 flat_rates=flat_rates if isinstance(flat_rates, dict) else {},
                                 pools=display_pools,
                                 available_pairs=available_pairs,
                                 form_data=data,
                                 from_amount=from_amount)

        rates = rates_source
        pair = f"{data['from_currency']}_{data['to_currency']}"
        rate_info = rates.get(pair)

        if rate_info is None:
            return render_template('index.html',
                                 error=f"Exchange pair {pair} not supported in {data['rate_mode']} mode.",
                                 currencies=sorted(list(currencies)),
                                 dynamic_rates=dynamic_rates_data if isinstance(dynamic_rates_data, dict) else {},
                                 flat_rates=flat_rates if isinstance(flat_rates, dict) else {},
                                 pools=display_pools,
                                 available_pairs=available_pairs,
                                 form_data=data,
                                 from_amount=from_amount)

        from_currency = data['from_currency']
        rate_value = rate_info.get('rate')
        svc_fee_value = rate_info.get('svc_fee')

        if rate_value is None or svc_fee_value is None:
            return render_template('index.html',
                                 error=f"Incomplete rate information for pair {pair}.",
                                 currencies=sorted(list(currencies)),
                                 dynamic_rates=dynamic_rates_data if isinstance(dynamic_rates_data, dict) else {},
                                 flat_rates=flat_rates if isinstance(flat_rates, dict) else {},
                                 pools=display_pools,
                                 available_pairs=available_pairs,
                                 form_data=data,
                                 from_amount=from_amount)

        calculation = {
            'from_currency': from_currency,
            'to_currency': data['to_currency'],
            'rate': None,
            'rate_mode': data['rate_mode'],
            'svc_fee': None
        }
        try:
            calculation['rate'] = float(rate_value)
            calculation['svc_fee'] = float(svc_fee_value)
        except (ValueError, TypeError):
            return render_template('index.html',
                                 error=f"Invalid numeric data received from API for pair {pair}.",
                                 currencies=sorted(list(currencies)),
                                 dynamic_rates=dynamic_rates_data if isinstance(dynamic_rates_data, dict) else {},
                                 flat_rates=flat_rates if isinstance(flat_rates, dict) else {},
                                 pools=display_pools,
                                 available_pairs=available_pairs,
                                 form_data=data,
                                 from_amount=from_amount)

        if from_amount:
            try:
                from_amount_float = float(from_amount)
                if calculation['svc_fee'] is None or calculation['rate'] is None:
                    raise ValueError("Service fee or rate is missing")
                fee_percentage = calculation['svc_fee'] / 100
                fee_amount = from_amount_float * fee_percentage
                usable_amount = from_amount_float - fee_amount
                to_amount = usable_amount * calculation['rate']

                calculation['from_amount'] = from_amount_float
                calculation['to_amount'] = to_amount
                calculation['fee_amount'] = fee_amount
            except ValueError:
                return render_template('index.html',
                                     error="Invalid amount entered",
                                     currencies=sorted(list(currencies)),
                                     dynamic_rates=dynamic_rates_data if isinstance(dynamic_rates_data, dict) else {},
                                     flat_rates=flat_rates if isinstance(flat_rates, dict) else {},
                                     pools=display_pools,
                                     available_pairs=available_pairs,
                                     form_data=data,
                                     from_amount=from_amount)

        return render_template('index.html',
                             currencies=sorted(list(currencies)),
                             dynamic_rates=dynamic_rates_data if isinstance(dynamic_rates_data, dict) else {},
                             flat_rates=flat_rates if isinstance(flat_rates, dict) else {},
                             pools=display_pools,
                             available_pairs=available_pairs,
                             form_data=data,
                             from_amount=from_amount,
                             calculation=calculation,
                             reserves=reserves,
                             erc20_currencies=erc20_currencies,
                             donation=get_random_donation())
    else: 
        if from_amount:
            data['amount'] = from_amount

        response = await fetch_api('create', 'POST', data)
        if 'error' in response or 'orderid' not in response:
            error_msg = response.get('error', 'Failed to create order. Missing order ID.')
            return render_template('index.html',
                                 error=error_msg,
                                 currencies=sorted(list(currencies)),
                                 dynamic_rates=dynamic_rates_data if isinstance(dynamic_rates_data, dict) else {},
                                 flat_rates=flat_rates if isinstance(flat_rates, dict) else {},
                                 pools=display_pools,
                                 available_pairs=available_pairs,
                                 form_data=data,
                                 from_amount=from_amount)
        return redirect(url_for('order', order_id=response['orderid']))

@app.route('/order/<order_id>', methods=['GET', 'POST'])
async def order(order_id):
    response = {}
    error = None

    if request.method == 'POST':
        if 'autorefresh' in request.form:
            session['autorefresh'] = request.form['autorefresh']
            return redirect(url_for('order', order_id=order_id))

        action = request.form.get('action')
        if action == 'refund':
            response = await fetch_api('order/refund', 'POST', {'orderid': order_id})
        elif action == 'refund_confirm':
            response = await fetch_api('order/refund_confirm', 'POST', {
                'orderid': order_id,
                'refund_address': request.form['refund_address']
            })
        elif action == 'remove':
            response = await fetch_api('order/remove', 'POST', {'orderid': order_id})

        if response and 'error' in response:
            error = response['error']

    order_data = await fetch_api('order', data={'orderid': order_id})
    if 'error' in order_data:
        return render_template('order.html', error=order_data['error'])

    qr_code = generate_qr_code(order_data['from_addr']) if order_data.get('from_addr') else None
    support_messages = await fetch_api('order/support_messages', data={'orderid': order_id})
    if 'error' in support_messages:
        support_messages = []

    autorefresh = session.get('autorefresh', 'on')

    return render_template('order.html',
                          order=order_data,
                          qr_code=qr_code,
                          support_messages=support_messages,
                          error=error,
                          autorefresh=autorefresh)

@app.route('/download_guarantee_letter/<order_id>')
async def download_guarantee_letter(order_id):
    guarantee_text = await fetch_api('order/fetch_guarantee', data={'orderid': order_id})
    if isinstance(guarantee_text, dict) and 'error' in guarantee_text:
        return render_template('order.html', error=guarantee_text['error'], order_id=order_id)
    
    buffer = StringIO()
    buffer.write(guarantee_text)
    buffer.seek(0)
    return send_file(
        BytesIO(buffer.getvalue().encode('utf-8')),
        as_attachment=True,
        download_name=f"guarantee_letter_{order_id}.txt",
        mimetype='text/plain'
    )

@app.route('/send_support_message_form/<order_id>', methods=['POST'])
async def send_support_message_form(order_id):
    message = request.form.get('message', '').strip()
    if not message:
        return render_template('order.html', error='Please enter a message', order_id=order_id)
    
    response = await fetch_api('order/support_message', 'POST', {
        'orderid': order_id,
        'supportmessage': message
    })
    
    return redirect(url_for('order', order_id=order_id))

@app.route('/revalidate_address_form/<order_id>', methods=['POST'])
async def revalidate_address_form(order_id):
    new_address = request.form.get('new_address', '').strip()
    if not new_address:
        return render_template('order.html', error='Please enter a new address', order_id=order_id)
    
    response = await fetch_api('order/revalidate_address', 'POST', {
        'orderid': order_id,
        'to_address': new_address
    })
    
    if 'error' in response:
        return render_template('order.html', error=response['error'], order_id=order_id)
    
    return redirect(url_for('order', order_id=order_id))

@app.route('/faq')
def faq():
    return render_template('faq.html')

@app.route('/contact', methods=['GET', 'POST'])
async def contact():
    if request.method == 'POST':
        email = request.form.get('email', '')
        message = request.form.get('supportmessage', '')
        return render_template('contact.html', success="Your message has been sent successfully!")
    
    return render_template('contact.html')

@app.route('/api')
def api_docs():
    return render_template('api.html')

@app.route('/rates')
def rates():
    return render_template('rates.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)