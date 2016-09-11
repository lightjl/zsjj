import talib
import numpy as np
import pandas as pd
import tradestat
import json
from six import StringIO
'''
================================================================================
总体回测前
================================================================================
'''
# 初始化函数，设定要操作的股票、基准等等
#总体回测前要做的事情
def initialize(context):
    set_params()                             # 设置策略常量
    set_variables()                          # 设置中间变量
    set_backtest()                           # 设置回测条件
    # 加载统计模块
    if g.flag_stat:
        g.trade_stat = tradestat.trade_stat()
    g.pe = pd.read_csv(StringIO(read_file('hscei.csv')),index_col=[0]) 

#1 
#设置策略参数
def set_params():
    g.num_stocks = 5                         # 每次调仓选取的最大股票数量
    g.flag_stat = True                      # 默认不开启统计

#2
#设置中间变量
def set_variables():
    g.t = 0                                  # 记录回测运行的天数
    g.if_trade = False                       # 当天是否交易

#3
#设置回测条件
def set_backtest():
    set_option('use_real_price',True)        # 用真实价格交易
    log.set_level('order','debug')           # 设置报错等级

    
'''
================================================================================
每天开盘前
================================================================================
'''
#每天开盘前要做的事情
def before_trading_start(context):

    set_slip_fee(context)                 # 设置手续费与手续费
    # 设置可行股票池
    g.feasible_stocks = ['510900.XSHG']   # 易方达恒生ETF



    
#5
# 根据不同的时间段设置滑点与手续费
# 输入：context（见API）
# 输出：none
def set_slip_fee(context):
    # 将滑点设置为0
    set_slippage(FixedSlippage(0)) 
    # 根据不同的时间段设置手续费
    dt=context.current_dt
    if dt>datetime.datetime(2013,1, 1):
        set_commission(PerTrade(buy_cost=0.0003, sell_cost=0.0003, min_cost=0.1)) 
        
    elif dt>datetime.datetime(2011,1, 1):
        set_commission(PerTrade(buy_cost=0.001, sell_cost=0.001, min_cost=0.1))
            
    elif dt>datetime.datetime(2009,1, 1):
        set_commission(PerTrade(buy_cost=0.002, sell_cost=0.002, min_cost=0.1))
    else:
        set_commission(PerTrade(buy_cost=0.003, sell_cost=0.003, min_cost=0.1))
        
'''
================================================================================
每天交易时
================================================================================
'''
# 每天回测时做的事情
def handle_data(context,data):
    
    list_can_buy = stocks_can_buy(context)
    # 待卖出的股票，list类型
    list_to_sell = stocks_to_sell(context, data)

    list_to_buy = pick_buy_list(context, data, list_can_buy, list_to_sell)
    # 卖出操作
    sell_operation(context, list_to_sell)    

    buy_operation(context, list_to_buy)
    
def stocks_can_buy(context):
    list_to_buy = []
    # g.feasible_stocks

    return list_to_buy
    
#8
# 获得卖出信号
# 输入：context（见API文档）, list_to_buy为list类型，代表待买入的股票
# 输出：list_to_sell为list类型，表示待卖出的股票
def stocks_to_sell(context, data):
    list_to_sell = []
    list_hold = context.portfolio.positions.keys()
    if len(list_hold) == 0:
        return list_to_sell
    
    for i in list_hold:
        if context.portfolio.positions[i].sellable_amount == 0:
            continue
        if context.portfolio.positions[i].avg_cost *0.95 >= data[i].close:
            #亏损 5% 卖出
            list_to_sell.append(i)
        if context.portfolio.positions[i].avg_cost *1.1 <= data[i].close:
            #赚 10% 卖出
            list_to_sell.append(i)
    return list_to_sell
    
# 获得买入的list_to_buy
# 输入list_can_buy 为list，可以买的队列
# 输出list_to_buy 为list，买入的队列
def pick_buy_list(context, data, list_can_buy, list_to_sell):
    list_to_buy = []
    # 要买数 = 可持数 - 持仓数 + 要卖数
    buy_num = g.num_stocks - len(context.portfolio.positions.keys()) + len(list_to_sell)
    if buy_num <= 0:
        return list_to_buy
    # 得到一个dataframe：index为股票代码，data为相应的PEG值
    # 处理-------------------------------------------------
    current_data = get_current_data()
    ad_num = 0;
    for i in list_can_buy:
        if i not in context.portfolio.positions.keys():
            # 没有持仓这股票, 假如这股票此时红盘就买入
            if data[i].close > current_data[i].day_open:
                list_to_buy.append(i)
                ad_num = ad_num + 1
        if ad_num >= buy_num:
            break
    return list_to_buy

# 自定义下单
# 根据Joinquant文档，当前报单函数都是阻塞执行，报单函数（如order_target_value）返回即表示报单完成
# 报单成功返回报单（不代表一定会成交），否则返回None
def order_target_value_(security, value):
    if value == 0:
        log.debug("Selling out %s" % (security))
    else:
        log.debug("Order %s to value %f" % (security, value))
        
    # 如果股票停牌，创建报单会失败，order_target_value 返回None
    # 如果股票涨跌停，创建报单会成功，order_target_value 返回Order，但是报单会取消
    # 部成部撤的报单，聚宽状态是已撤，此时成交量>0，可通过成交量判断是否有成交
    return order_target_value(security, value)
    
# 平仓，卖出指定持仓
# 平仓成功并全部成交，返回True
# 报单失败或者报单成功但被取消（此时成交量等于0），或者报单非全部成交，返回False
def close_position(position):
    security = position.security
    order = order_target_value_(security, 0) # 可能会因停牌失败
    if order != None:
        if order.filled > 0 and g.flag_stat:
            # 只要有成交，无论全部成交还是部分成交，则统计盈亏
            g.trade_stat.watch(security, order.filled, position.avg_cost, position.price)

    return False
    
#9
# 执行卖出操作
# 输入：list_to_sell为list类型，表示待卖出的股票
# 输出：none
def sell_operation(context, list_to_sell):
    for stock_sell in list_to_sell:
        position = context.portfolio.positions[stock_sell]
        close_position(position)
        
#10
# 执行买入操作
# 输入：context(见API)；list_to_buy为list类型，表示待买入的股票
# 输出：none
def buy_operation(context, list_to_buy):
    for stock_buy in list_to_buy:
        # 为每个持仓股票分配资金
        g.capital_unit=context.portfolio.portfolio_value/g.num_stocks
        # 买入在"待买股票列表"的股票
        order_target_value(stock_buy, g.capital_unit)
        
'''
================================================================================
每天交易后
================================================================================
'''
def after_trading_end(context):
    if g.flag_stat:
        g.trade_stat.report(context)
        