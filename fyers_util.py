from fyers_apiv3 import fyersModel
import os
import pandas as pd

columns_names = ['Date','Open','High','Low','Close','Volume']

def authenticate():
    client_id="Z4O9BSFX7K-100"
    secret_key="4YW3EMFX5U"
    redirect_uri="https://www.google.com/"
    response_type="code"
    session = fyersModel.SessionModel(client_id=client_id,secret_key=secret_key,redirect_uri=redirect_uri,response_type=response_type)
    print(session.generate_authcode())

def authorization(url):
    grant_type = "authorization_code"
    client_id="Z4O9BSFX7K-100"
    secret_key="4YW3EMFX5U"
    redirect_uri="https://www.google.com/"
    response_type="code"
    auth_code=url.split('&')[2].split('=')[1]
    #print(auth_code)
    session = fyersModel.SessionModel(client_id=client_id,secret_key=secret_key, redirect_uri=redirect_uri, response_type=response_type, grant_type=grant_type)
    session.set_token(auth_code)
    token=session.generate_token()
    #print('token->',token)
    print('token->',token['access_token'])
    #access_token = session.generate_token()['access_token']
    access_token=token['access_token']
    file1 = open("D:/bayareddy/learn/AlgoTrading/backtesting/access_token.txt","w")
    file1.write(access_token)
    file1.close()
    #script_dir = os.path.dirname(os.path.abspath(__file__))
    #file_path = os.path.join(script_dir, 'access_token.txt')
    #with open(file_path, 'r') as file:
        #content = file.read()
        #file.write(access_token)
        #file.close()
    
    print("Access token updated successfully in File")

    
def fyersObj():
    file_r = open("D:/bayareddy/learn/AlgoTrading/backtesting/access_token.txt","r+")
    fyers = fyersModel.FyersModel(client_id="Z4O9BSFX7K-100", is_async=False, token=file_r.read(), log_path=os.getcwd())
    return fyers


def getNetPostions(symbol):
    sym='NSE:'+symbol+'-EQ'
    response = fyersObj().positions()
    #print(response['overall']['count_open'])
    if(response['overall']['count_open']) >0:
        print(response['netPositions'])
        netposits=response['netPositions']
        for row in netposits:
            #print('row->',row)
            print('dayBuyQty->',row['dayBuyQty'],'daySellQty->',row['daySellQty'])
            if(sym == row['symbol'] and row['dayBuyQty'] !=row['daySellQty']):
                #symbol=row['symbol']
                if(row['dayBuyQty'] >row['daySellQty']):
                    qty=(row['dayBuyQty']-row['daySellQty'])
                    print(row['symbol'],'Open Buy Positions:',qty)
                    return qty,0
                    #closeBuyPostions(symbol=row['symbol'])
                    #fu.placeOrderwith_symbol(symbol=row['symbol'],quantity=qty,side=-1, order_type=2)
                else:
                    qty=(row['daySellQty']-row['dayBuyQty'])
                    print(row['symbol'],'Open Sell Positions:',qty)
                    return 0,qty
                    #fu.placeOrderwith_symbol(symbol=symbol,quantity=qty,side=1, order_type=2)
    else:
        print('open Net Postions are not there')
        return 0,0

def getAllNetPostions():
    response = fyersObj().positions()
    #print(response['overall']['count_open'])
    if(response['overall']['count_open']) >0:
        #print(response['netPositions'])
        netposits=response['netPositions']
        for row in netposits:
            print('row->',row)
            print('dayBuyQty->',row['dayBuyQty'])
            print('daySellQty->',row['daySellQty'])
            if(row['dayBuyQty'] !=row['daySellQty']):
                symbol=row['symbol']
                if(row['dayBuyQty'] >row['daySellQty']):
                    qty=(row['dayBuyQty']-row['daySellQty'])
                    print(symbol,'Open Buy Positions:',qty)
                    return qty,0
                    #closeBuyPostions(symbol=row['symbol'])
                    #fu.placeOrderwith_symbol(symbol=row['symbol'],quantity=qty,side=-1, order_type=2)
                else:
                    qty=(row['daySellQty']-row['dayBuyQty'])
                    print(row['symbol'],'Open Sell Positions:',qty)
                    return 0,qty
                    #fu.placeOrderwith_symbol(symbol=symbol,quantity=qty,side=1, order_type=2)



#                  Order Management - Start

def placeOrder(stock_code,quantity,side, order_type=2, limitPrice=0,stopPrice=0):
    #side =1 -BUY, -1 -Sell  type: 1 -Limit Order, 2 -Market Order, 3 -Stop Order (SL-M), 4 - Stoplimit Order (SL-L)
    data = { "symbol":"NSE:"+stock_code+"-EQ", "qty":quantity,           "type":order_type,           "side":side,
             "productType":"INTRADAY",         "limitPrice":limitPrice,  "stopPrice":stopPrice,
             "validity":"DAY",                 "disclosedQty":0,         "offlineOrder":False,}
    print('Input Payload: ',data)
    response = fyersObj().place_order(data=data)
    print('Order Response :',response)
    return response

def placeOrderwith_symbol(symbol,quantity,side, order_type=2, limitPrice=0,stopPrice=0):
    #side =1 -BUY, -1 -Sell  type: 1 -Limit Order, 2 -Market Order, 3 -Stop Order (SL-M), 4 - Stoplimit Order (SL-L)
    data = { "symbol":symbol,                  "qty":quantity,            "type":order_type,           "side":side,
             "productType":"INTRADAY",         "limitPrice":limitPrice,   "stopPrice":stopPrice,
             "validity":"DAY",                 "disclosedQty":0,          "offlineOrder":False,}
    print('Input Payload: ',data)
    response = fyersObj().place_order(data=data)
    print('Order Response :',response)
    return response

def placeMarketLimitOrder(stock_code,qty,side):
    #order_type 1->limit Order, 2-> MarketOrder
    order_reponse=placeOrder(stock_code=stock_code,quantity=qty,side=side, order_type=1, limitPrice=(getLastTradedPrice(stock_code)))
    print('Order Response:',order_reponse)
    order_comp_status_flag=True
    while(order_comp_status_flag):
        order_id=order_reponse['id']
        data = {"id":order_id}
        order_res = fyersObj().orderbook(data=data)
        print('order_res:',order_res)
        # Status 1 => Canceled, 2 => Traded / Filled, 3 => (Not used currently), 4 => Transit
        # 5 => Rejected, 6 => Pending, 7 => Expired
        if(order_res['orderBook'][0]['status']==6):
            #order_reponse=fu.placeOrder(stock_code=StockCode,quantity=1,side=1, order_type=1, limitPrice=(fu.getLastTradedPrice(StockCode)-5))
            data = {"id":order_id, "type":order_res['orderBook'][0]['type'], "limitPrice": getLastTradedPrice(stock_code), 
                    "qty":order_res['orderBook'][0]['remainingQuantity']}
            response = fyersObj().modify_order(data=data)
            print('Modify Order Response:',response)
        else:
            order_comp_status_flag=False




#                       Order Management  End


def history(symbol, time_frame,range_from, range_to):
    #print('Stock Name:',symbol,'Timeframe:',time_frame,'From Date:',range_from,'To Date',range_to)
    df = fyersObj().history({"symbol":symbol, "resolution":time_frame, "date_format":"1", "range_from":range_from, "range_to":range_to, "cont_flag":"1"})
    return df
    




def stock_hist_DateFmt_symbol(symbol, time_frame,range_from, range_to):
    print('Stock Name:',symbol,'Timeframe:',time_frame,'From Date:',range_from,'To Date',range_to)
    df = fyersObj().history({"symbol":symbol, "resolution":time_frame, "date_format":"1", "range_from":range_from, "range_to":range_to, "cont_flag":"1"})
    return df



def get_stock_hist(stock_name, time_frame,range_from, range_to):
    print('Stock Name:',stock_name,'Timeframe:',time_frame,'From Date:',range_from,'To Date',range_to)
    df = fyersObj().history({"symbol":"NSE:"+stock_name+"-EQ", "resolution":time_frame, "date_format":"1", "range_from":range_from, "range_to":range_to, "cont_flag":"1"})
    #print(df)
    if df['s']=='no_data':
        return pd.DataFrame(df['candles'])
    if df['code']==-300 :
        df = fyers.history({"symbol":"NSE:"+stock_name+"-BE", "resolution":time_frame, "date_format":"1", "range_from":range_from, "range_to":range_to, "cont_flag":"1"})
        if df['code']==-300 :
            #print(df)
            return pd.DataFrame(columns = columns_names)
    #print(df)
    return pd.DataFrame(df['candles'])

def get_stock_hist_DateFmt(stock_name, time_frame,range_from, range_to):
    print('Stock Name:',stock_name,'Timeframe:',time_frame,'From Date:',range_from,'To Date',range_to)
    df = fyersObj().history({"symbol":"NSE:"+stock_name+"-EQ", "resolution":time_frame, "date_format":"1", "range_from":range_from, "range_to":range_to, "cont_flag":"1"})
    if df['code']==-300 :
        df = fyersObj().history({"symbol":"NSE:"+stock_name+"-BE", "resolution":time_frame, "date_format":"1", "range_from":range_from, "range_to":range_to, "cont_flag":"1"})
        if df['code']==-300 :
            #print(df)
            return pd.DataFrame(columns = columns_names)
    #print(df)
    histData=pd.DataFrame(df['candles'])
    histData.columns=columns_names
    histData['Date']=pd.to_datetime(histData['Date'],unit='s')
    histData.Date=(histData.Date.dt.tz_localize('UTC').dt.tz_convert('Asia/kolkata'))
    histData['Date']=histData['Date'].dt.tz_localize(None)
    return histData

def getQuotes(StockName, exchange='NSE',type="EQ"):
    data = {"symbols":exchange+":"+StockName+"-"+type}
    response = fyersObj().quotes(data=data)
    return response

#qt=getQuotes('SBIN')
#print(qt)
#print(qt['d'][0]['v']['lp'])
def getLastTradedPrice(StockName, exchange='NSE'):
    return getQuotes(StockName)['d'][0]['v']['lp']
