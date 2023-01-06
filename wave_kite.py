import random
import math
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from finta import TA as ta
from fyers_api import fyersModel
from fyers_api import accessToken
from fyers_api.Websocket import ws
import calendar
import os
from os import environ, symlink
import time
import threading
import requests
import json
from urllib.parse import urlparse, parse_qs
import sys
from kite_trade import *
from flask import Flask, request, render_template, session, redirect
from flask_socketio import SocketIO
from flask_lt import run_with_lt
from collections import Counter
import talib

app = Flask(__name__, template_folder='.')
socket = SocketIO(app, ping_timeout=5, ping_interval=5, cors_allowed_origins="*")
run_with_lt(socket, 'vivek-algo')
INDEX_MAP = {
    "NIFTY": "NSE:NIFTY 50",
    "BANKNIFTY": "NSE:NIFTY BANK",
}


class waveAlgo():

    def __init__(self):
        self.is_android = False
        if 'ANDROID_BOOTLOGO' in environ:
            self.is_android = True

        def check_last_expiry(day):
            month = calendar.monthcalendar(datetime.today().year, datetime.today().month)

            thrusday = max(month[-1][calendar.THURSDAY], month[-2][calendar.THURSDAY])
            return thrusday == day

        def get_next_weekday(startdate, weekday):
            """
            @startdate: given date, in format '2013-05-25'
            @weekday: week day as a integer, between 0 (Monday) to 6 (Sunday)
            """
            d = datetime.strptime(startdate, '%Y-%m-%d')
            t = timedelta((7 + weekday - d.weekday()) % 7)
            return (d + t)

        self.funds = 15000
        self.target_profit = 2000
        self.kite_order = False;
        self.resolution = 15
        self.wto_diff = []
        next_expiry = get_next_weekday(date.today().strftime("%Y-%m-%d"), 3)
        if not check_last_expiry(next_expiry.day):
            self.next_expiry = f"{next_expiry.strftime('%y')}{int(next_expiry.strftime('%m'))}{next_expiry.strftime('%d')}"
        else:
            self.next_expiry = f"{next_expiry.strftime('%y')}{int(next_expiry.strftime('%b'))}"

        # enctoken = input("Enter Token: ")
        enctoken = "+20Sy+UzmcGu0/E+F77qqSDCRXHdU9hb4AptVkRLzMjk7YniCx0ZarVWwEQ79w1/q8kCRHxVQmVJIx39CfWdi2AEGbStLAAmhLFyrdKCPU6liOuaJmj3wg=="
        self.kite = KiteApp(enctoken=enctoken)
        self._setup_fyers()
        self._setup_tradebook()

        threading.Thread(target=self.refresh).start()
        # threading.Thread(target=self.temp_update_ltp).start()

    def temp_update_ltp(self):
        starttime = time.time()
        while True:
            try:
                tradebook = self.tradebook[
                    self.tradebook['orderId'].map(
                        lambda x: str(x).startswith('NFO'))]  # & self.tradebook['unsubscribe']]
                if not tradebook.empty:
                    tradebook = tradebook.loc[random.choice(list(tradebook.index.values))]
                    self._update_ltp(
                        {tradebook['orderId']: {"symbol": tradebook['orderId'], "last_price": random.randint(
                            tradebook['ltp'] - 5, tradebook['ltp'] + 5)}})
            finally:
                time.sleep(1 - ((time.time() - starttime) % 1))

    def _setup_fyers(self):
        username = "XA36717"
        password = "Amod@fyres1"
        pin = "4321"
        client_id = "OUQC9PC52D-100"
        secret_key = "20NPHCNQDE"
        redirect_uri = "https://trade.fyers.in/api-login/redirect-uri/index.html"
        response_type = "code"
        headers = {
            "accept": "application/json",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.45 Safari/537.36",
            "accept-language": "en-US,en;q=0.9",
        }

        s = requests.Session()
        s.headers.update(headers)

        data1 = f'{{"fy_id":"{username}","password":"{password}","app_id":"2","imei":"","recaptcha_token":""}}'
        r1 = s.post("https://api.fyers.in/vagator/v1/login", data=data1)
        assert r1.status_code == 200, f"Error in r1:\n {r1.json()}"

        request_key = r1.json()["request_key"]
        data2 = f'{{"request_key":"{request_key}","identity_type":"pin","identifier":"{pin}","recaptcha_token":""}}'
        r2 = s.post("https://api.fyers.in/vagator/v1/verify_pin", data=data2)
        assert r2.status_code == 200, f"Error in r2:\n {r2.json()}"

        headers = {"authorization": f"Bearer {r2.json()['data']['access_token']}",
                   "content-type": "application/json; charset=UTF-8"}
        data3 = f'{{"fyers_id":"{username}","app_id":"{client_id[:-4]}","redirect_uri":"{redirect_uri}","appType":"100","code_challenge":"","state":"abcdefg","scope":"","nonce":"","response_type":"code","create_cookie":true}}'
        r3 = s.post("https://api.fyers.in/api/v2/token", headers=headers, data=data3)
        assert r3.status_code == 308, f"Error in r3:\n {r3.json()}"

        parsed = urlparse(r3.json()["Url"])
        auth_code = parse_qs(parsed.query)["auth_code"][0]

        session = accessToken.SessionModel(client_id=client_id, secret_key=secret_key, redirect_uri=redirect_uri,
                                           response_type="code", grant_type="authorization_code")
        session.set_token(auth_code)
        response = session.generate_token()
        access_token = response["access_token"]
        print("Got the fyers access token!")
        self.access_token = client_id + ":" + access_token
        self.data_type = "symbolData"
        self.fyers = fyersModel.FyersModel(client_id=client_id, token=access_token, log_path=os.getcwd())

    def _setup_tradebook(self):
        self.directory = f"{date.today().strftime('%Y-%m-%d')}"
        self.path = os.path.join(os.getcwd(), f'algo/{self.directory}')
        self.tradebook_path = os.path.join(self.path, "kwaveAlgo.csv")
        self.tradebook = pd.DataFrame([],
                                      columns=['orderId', 'symbol', 'strikePrice', 'side', 'investment', 'buy_price',
                                               'qty', 'stoploss', 'target', 'exit_price', 'ltp', 'profit_loss',
                                               'remark',
                                               'unsubscribe', 'entry_time', 'exit_time',
                                               'remaining_balance', 'kite_order'])
        print(
            f"Run This in Powershell For LogBook\n===============\nGet-Content -Path {self.tradebook_path.replace('csv', 'log')} -Wait")
        if not os.path.exists(self.path):
            os.makedirs(self.path)
        if not os.path.exists(self.tradebook_path):
            self.tradebook.loc[0] = ['NFO:Profit', '', '', '', '', '', '', '', '', '', '', 0, '', 'False', '23:59:59',
                                     '',
                                     self.funds, False]
            self.tradebook = self.tradebook.to_csv(self.tradebook_path, index=False)
        self.tradebook = pd.read_csv(self.tradebook_path)
        if len(self.tradebook.index) > 0:
            self.actual_profit = self.tradebook[
                self.tradebook['orderId'].map(
                    lambda x: str(x).startswith('NFO:') and not str(x).startswith('NFO:Profit'))][
                'profit_loss'].sum()
            fyers_profit = self.tradebook[
                self.tradebook['orderId'].map(
                    lambda x: str(x).startswith('NFO:') and not str(x).startswith('NFO:Profit')) &
                self.tradebook["kite_order"] != False]['profit_loss'].sum()
            print(f"Current Profit:{self.actual_profit}\n Fyers Profit: {fyers_profit}\n")
            tradebook = self.tradebook[
                self.tradebook['orderId'].map(lambda x: str(x).startswith('NFO')) & self.tradebook['unsubscribe']]
            self.symbols = list(tradebook['orderId'].values)
            self.balance = self._calculate_balance()
            print(f"Remaining Balance: {self.balance}\n")
            if self.kite_order and fyers_profit >= self.target_profit:
                print(f"Switiching to Papertrade only as Target profit is achived")
                self.kite_order = False

    def _calculate_balance(self):
        self.actual_profit = self.tradebook[
            self.tradebook['orderId'].map(lambda x: str(x).startswith('NFO:') and not str(x).startswith('NFO:Profit'))]
        if self.actual_profit.empty:
            self.actual_profit = 0
        else:
            self.actual_profit = self.actual_profit['profit_loss'].sum()
        return (self.funds + self.actual_profit) - self.tradebook.query("unsubscribe == True").investment.sum()

    def refresh(self):
        # threading.Thread(target=self._place_order).start()
        starttime = time.time()
        while True:
            try:
                t = threading.Thread(target=self._place_order)
                t.start()
            except:
                pass
            finally:
                pass
                print(f"Refreshed at {datetime.now().strftime('%H:%M:%S')}")
                time.sleep(2 - ((time.time() - starttime) % 2))

    def _get_wto(self, symbol):
        ltp = self.kite.quote(symbol).get(symbol)
        instrument_token = ltp.get('instrument_token')
        ltp = ltp.get('last_price')
        from_date = date.today() - timedelta(days=4)
        to_date = date.today()
        nohlc = pd.DataFrame(
            self.kite.historical_data(instrument_token, from_date=from_date, to_date=to_date, interval="15minute"))
        nohlc = nohlc.iloc[:, :5]
        nohlc.rename(columns={1: "open", 2: "high", 3: "low", 4: "close"}, inplace=True)
        nclose = nohlc['close'].values
        nwto = ta.WTO(nohlc)
        ao = ta.AO(nohlc)
        psar = ta.PSAR(nohlc)
        nohlc['sr'] = ta.STOCH(nohlc)
        nohlc['sr'] = ta.STOCHD(nohlc)
        nohlc['ao'] = ao
        nohlc['psar'] = psar['psar']
        nohlc['wt1'] = nwto['WT1.']
        nohlc['wt2'] = nwto['WT2.']
        nohlc['wtdiff'] = nwto['WT1.'] - nwto['WT2.']
        nohlc['ce_sl'] = nohlc['low'].round()[-2:-1].values[0]
        nohlc['pe_sl'] = nohlc['high'].round()[-2:-1].values[0]
        nohlc['prev_candle_diff'] = (nohlc['close'] - nohlc['open']).round()[-2:-1].values[0]
        nohlc['prev_close'] = nohlc['close'].round()[-2:-1].values[0]
        return nohlc.round(2)

    def _get_ema_values(self, symbol):
        old_symbol = symbol
        try:
            # self.tradebook = self.tradebook[self.tradebook['orderId'].map(lambda x: str(x).startswith('NFO'))]
            symbol = INDEX_MAP[symbol]
            buy_sell_signal = self._get_wto(symbol)
            last_wto_val = pd.DataFrame({"a": buy_sell_signal['ao']}).tail(2).round(2)
            is_increasing = last_wto_val.apply(lambda x: x.is_monotonic_increasing).bool()
            is_decreasing = last_wto_val.apply(lambda x: x.is_monotonic_decreasing).bool()
            ltp = self.kite.ltp(symbol).get(symbol, {}).get('last_price')
            buy_sell_signal['ltp'] = ltp

            wto_long_index = buy_sell_signal.loc[
                np.where((buy_sell_signal['wt1'] > buy_sell_signal['wt2']))].tail(1)
            wto_short_index = buy_sell_signal.loc[
                np.where((buy_sell_signal['wt1'] < buy_sell_signal['wt2']))].tail(1)

            long_index = buy_sell_signal.loc[
                np.where((buy_sell_signal['psar'] < ltp))].tail(1)
            short_index = buy_sell_signal.loc[
                np.where((buy_sell_signal['psar'] > ltp))].tail(1)

            if not long_index.empty:
                long_index = long_index.index.values[0]
            else:
                long_index = 0
            if not short_index.empty:
                short_index = short_index.index.values[0]
            else:
                short_index = 0

            if not wto_long_index.empty:
                wto_long_index = wto_long_index.index.values[0]
            else:
                wto_long_index = 0
            if not wto_short_index.empty:
                wto_short_index = wto_short_index.index.values[0]
            else:
                wto_short_index = 0
            is_long_wto = (wto_long_index > wto_short_index)
            is_short_wto = (wto_long_index < wto_short_index)
            long_counter_list = [is_increasing, (long_index > short_index), is_long_wto]
            short_counter_list = [is_decreasing, (long_index < short_index), is_short_wto]
            long_counter_list = Counter(long_counter_list)
            short_counter_list = Counter(short_counter_list)
            is_long = list([item for item in long_counter_list if long_counter_list[item] > 1])
            is_short = list([item for item in short_counter_list if short_counter_list[item] > 1])
            is_long = all(is_long)
            is_short = all(is_short)

            buy_sell_signal['ready_ce'] = (buy_sell_signal['prev_close'].tail(1).values[0] < ltp and is_long and abs(
                buy_sell_signal['wtdiff'].tail(1).values[0]) > 2)
            buy_sell_signal['ready_pe'] = (buy_sell_signal['prev_close'].tail(1).values[0] > ltp and is_short and abs(
                buy_sell_signal['wtdiff'].tail(1).values[0]) > 2)

            if not self.is_android:
                print(buy_sell_signal.tail(1).to_string(), self.actual_profit)
                print("============================")
            t = self.tradebook.query(f"symbol == '{old_symbol}' and side == 'PE' and unsubscribe != False")
            if not t.empty:
                for index, row in t.iterrows():
                    if buy_sell_signal.tail(1)['pe_sl'].values[0] < ltp:
                        self._orderUpdate(index, "Stoploss", f"{buy_sell_signal.tail(1)['pe_sl'].values[0]}  < {ltp}",
                                          row.ltp, old_symbol)
                        return False, False
                    elif is_long:
                        self._orderUpdate(index, "Exited", f"due to is_long", row.ltp, old_symbol)
                        return False, False
            t = self.tradebook.query(f"symbol == '{old_symbol}' and side == 'CE' and unsubscribe != False")
            if not t.empty:
                for index, row in t.iterrows():
                    if buy_sell_signal.tail(1)['ce_sl'].values[0] > ltp:
                        self._orderUpdate(index, "Stoploss", f"{buy_sell_signal.tail(1)['ce_sl'].values[0]}  > {ltp}",
                                          row.ltp, old_symbol)
                        return False, False
                    elif is_short:
                        self._orderUpdate(index, "Exited", f"due to is_short", row.ltp, old_symbol)
                        return False, False
            # if abs(buy_sell_signal['prev_candle_diff'].tail(1).values[0]) > 50:
            #     return False, False
            if buy_sell_signal['ready_ce'].tail(1).bool():
                return True, "CE"
            elif buy_sell_signal['ready_pe'].tail(1).bool():
                return True, "PE"
            else:
                return False, False

        except Exception as e:
            print(e)
            return False, False

    def _getStrike(self, ltp, side, qty):
        if side == "PE":
            return (math.ceil(ltp / qty) * qty) + qty
        else:
            return (math.floor(ltp / qty) * qty) - qty

    def get_seconds_to_close(self, timestamp):
        seconds = 300
        current_time = time.time()
        needed_timestamp = timestamp + seconds
        seconds_left = needed_timestamp - current_time
        return seconds_left

    def _loss_orders(self, symbol, side):
        s = INDEX_MAP[symbol]
        ltp = self.kite.quote(s).get(s)['last_price']
        lot = 50 if symbol != 'BANKNIFTY' else 100
        strikePrice = self._getStrike(ltp, side, lot)
        orderId = f'NFO:{symbol}{self.next_expiry}{strikePrice}{side}'
        try:
            last_exit = self.tradebook.query(f"symbol   == '{symbol}' and side == '{side}' and profit_loss < 0")[
                'exit_time'].tail(1)
            delta = timedelta(minutes=5)
            if not last_exit.empty and not last_exit.isna().bool() and not (datetime.now().time() > (
                    datetime.min + math.ceil(
                    (datetime.strptime(last_exit.values[0], "%H:%M:%S") - datetime.min) / delta) * delta).time()):
                print('exited')
                return False, False, False
            delta = timedelta(minutes=15)
            sl_order = self.tradebook.query(f"symbol == '{symbol}' and side == '{side}' and remark == 'Stop Loss Hit'")[
                'exit_time'].tail(1)
            if not sl_order.empty and not sl_order.isna().bool() and not (datetime.now().time() > (
                    datetime.min + math.ceil(
                    (datetime.strptime(sl_order.values[0], "%H:%M:%S") - datetime.min) / delta) * delta).time()):
                print("wait for next candle")
                return False, False, False
            return strikePrice, orderId, side
        except Exception as e:
            print(e)
            print(self.tradebook.query(f"symbol == '{symbol}' and side == '{side}' and remark == 'Stop Loss Hit'")[
                      'exit_time'].tail(1))
            return False, False, False

    def _place_order(self):
        if not (datetime.now().strftime('%H:%M') > '09:29'):
            return
        self._update_ltp()
        for symbol in ["NIFTY", "BANKNIFTY"]:
            is_valid_ema, side = self._get_ema_values(symbol)
            if not is_valid_ema:
                continue
            # if not (datetime.now().strftime('%H:%M') < '15:20'):
            #     continue
            strikePrice, orderId, side = self._loss_orders(symbol, side)
            if not strikePrice:
                continue
            if self.tradebook.query(f"orderId == '{orderId}' and unsubscribe != False").empty:
                ltp = self.kite.quote(orderId).get(orderId)['last_price']
                no_of_lots = int(self.funds / ((25 if symbol == "BANKNIFTY" else 50) * ltp))
                qty = (25 if symbol == "BANKNIFTY" else 50) * 1  # \\(2 if symbol == "BANKNIFTY" else 1)
                vals = {
                    'orderId': orderId,
                    "symbol": symbol,
                    'strikePrice': strikePrice,
                    'side': side,
                    'investment': ltp * qty,
                    'buy_price': ltp,
                    'qty': qty,
                    'stoploss': 0,
                    'target': 0,
                    'exit_price': 0,
                    'ltp': ltp,
                    'profit_loss': 60 * -1,
                    'remark': "",
                    "unsubscribe": True
                }
                target = ltp + 300
                stoploss = ltp - (ltp * 0.25)
                vals['target'] = target
                vals['stoploss'] = stoploss
                vals['entry_time'] = datetime.now().strftime("%H:%M:%S")
                vals['exit_time'] = np.nan
                vals['remaining_balance'] = 0
                vals['kite_order'] = False
                # balance = self.nifty_balance if symbol == "NIFTY" else self.bnnifty_balance
                cur_balance = self._calculate_balance()
                print(cur_balance)
                balance = 15000 if cur_balance > 15000 else cur_balance
                if ((vals['investment'] + 200) < balance):
                    self.balance -= vals['investment']
                    self.symbols.append(orderId)
                    if self.kite_order:
                        try:
                            print(
                                f"Placing kite order {orderId} with limit price {ltp} qty {qty} stoploss {stoploss} target {vals['target']}")
                            vals['kite_order'] = True
                            f_orderId = self._getOrderData(orderId, "B", qty)
                            print(f_orderId)
                        except Exception as e:
                            print(e)
                    self.tradebook = self.tradebook.append([vals], ignore_index=True)
                else:
                    print(f"Not Enough balance {balance} {orderId} {qty} {ltp}")

    def _getOrderData(self, order, signal, qty):
        transaction = self.kite.TRANSACTION_TYPE_BUY if signal == "B" else self.kite.TRANSACTION_TYPE_SELL
        return self.kite.place_order(tradingsymbol=order.replace("NFO:", ""),
                                     exchange=self.kite.EXCHANGE_NFO,
                                     transaction_type=transaction,
                                     quantity=int(qty),
                                     variety=self.kite.VARIETY_REGULAR,
                                     order_type=self.kite.ORDER_TYPE_MARKET,
                                     product=self.kite.PRODUCT_MIS,
                                     validity=self.kite.VALIDITY_DAY)

    def _orderUpdate(self, index, order_status, message, ltp, symbol):
        try:
            if self.tradebook.loc[index, 'orderId'] in self.symbols:
                if self.kite_order:
                    orderId = self.tradebook.loc[index, 'orderId']
                    qty = self.tradebook.loc[index, 'qty']
                    f_orderId = self._getOrderData(orderId, "S", qty)
                    print(f_orderId)
                self.symbols.remove(self.tradebook.loc[index, 'orderId'])
                self.tradebook.loc[index, 'qty'] = 0
                self.tradebook.loc[index, 'exit_price'] = ltp
                # print(f"\n Remaining Balance\n {self.balance}")
                self.tradebook.loc[index, 'remark'] = message
                self.tradebook.loc[index, 'unsubscribe'] = False
                self.tradebook.loc[index, 'exit_time'] = datetime.now().strftime("%H:%M:%S")
        except Exception as e:
            print(f"ERROR while orderupdate {e}")
        finally:
            self.balance = self._calculate_balance()
            self.tradebook.to_csv(self.tradebook_path, index=False)

    def exit_all_position(self):
        for index, row in self.tradebook.query("unsubscribe != False").iterrows():
            self._getOrderData(row['orderId'], "S", row['qty'])
        self.kite_order = False

    def _update_ltp(self, ltp_symbols=None):
        if not self.symbols:
            return
        if not ltp_symbols:
            ltp_symbols = self.kite.ltp(self.symbols) or {}
        for symbol, ltp in ltp_symbols.items():
            ltp = ltp['last_price']
            if self.kite_order and self.actual_profit >= self.target_profit:
                print("Switiching to Papertrade only as Target profit is achived")
                self.exit_all_position()
            for index, row in self.tradebook.query(
                    f"unsubscribe != False and orderId == '{symbol}'").iterrows():
                qty = self.tradebook.loc[index, 'qty']
                # i = 0 if self.tradebook.loc[index, 'side'] == 'CE' else 1
                self.tradebook.loc[index, 'profit_loss'] = (ltp * self.tradebook.loc[index, 'qty']) - \
                                                           self.tradebook.loc[
                                                               index, 'investment']
                change_target_sl = (5 if row.symbol == "BANKNIFTY" else 2)
                pro_loss = round((ltp * qty) - (self.tradebook.loc[index, 'buy_price'] * qty) - 60, 2)
                if pro_loss >= 800:  # (2000 if row.symbol == "BANKNIFTY" else 1200):
                    new_sl = ltp - change_target_sl
                    self.tradebook.loc[index, 'target'] += 5 if row.symbol == "NIFTY" else 15
                    self.tradebook.loc[index, 'stoploss'] = new_sl if new_sl > self.tradebook.loc[
                        index, 'stoploss'] else \
                        self.tradebook.loc[index, 'stoploss']
                if ltp > self.tradebook.loc[index, 'target']:
                    self._orderUpdate(index, "Compeleted", "Target Achived", ltp, row.symbol)
                if ltp < self.tradebook.loc[index, 'stoploss']:
                    self._orderUpdate(index, "StopLoss", "Stop Loss Hit", ltp, row.symbol)
                if self.tradebook.loc[index, 'qty'] > 0:
                    self.tradebook.loc[index, 'profit_loss'] = pro_loss  # (25 if row.symbol == "BANKNIFTY" else 50)
                else:
                    self.tradebook.loc[index, 'profit_loss'] = (self.tradebook.loc[index, 'exit_price'] * qty) - (
                            self.tradebook.loc[index, 'buy_price'] * qty) - 60
                self.actual_profit = self.tradebook[
                    self.tradebook['orderId'].map(
                        lambda x: str(x).startswith('NFO:') and not str(x).startswith('NFO:Profit'))][
                    'profit_loss'].sum()
                self.tradebook.loc[index, 'ltp'] = ltp  # if row.symbol == "NIFTY" else 15
                self.tradebook.loc[
                    self.tradebook.query("orderId == 'NFO:Profit'").index, "profit_loss"] = self.actual_profit
                self.tradebook.loc[
                    self.tradebook.query("orderId == 'NFO:Profit'").index, "remaining_balance"] = self.balance
        # tradebook.to_csv(self.tradebook_path, index=False)


if __name__ == '__main__':
    wv = waveAlgo()


    @app.route('/', methods=("POST", "GET"))
    def html_table():
        return render_template('sample.html', row_data=wv.tradebook.values.tolist())


    @socket.on('message')
    def data(msg):
        profit = wv.actual_profit
        res = render_template('data.html', row_data=wv.tradebook[1:].sort_values(by=['unsubscribe', 'entry_time'],
                                                                                 ascending=[False,
                                                                                            False]).values.tolist(),
                              profit=profit, balance=wv.balance)
        # time.sleep(1)
        return socket.emit("message", res, broadcast=True)


    try:
        socket.run(app, host='0.0.0.0')
    except KeyboardInterrupt:
        wv.tradebook.to_csv(wv.tradebook_path, index=False)
    finally:
        wv.tradebook.to_csv(wv.tradebook_path, index=False)