from decimal import Decimal
import random
from datetime import datetime, timedelta


class PaymentService:
    """
    支付服务层 - 模拟第三方支付平台
    在 MVP 阶段直接模拟支付成功，便于开发和测试
    未来接入真实支付平台时，只需替换本文件的实现即可
    """

    @staticmethod
    def pay(order_id, amount, payment_method='alipay'):
        """
        支付（一步完成）
        生成模拟交易号和支付时间，直接返回成功结果
        """
        import time
        time.sleep(0.1)

        trade_no = f"PAY{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
        return {
            'success': True,
            'trade_no': trade_no,
            'trade_status': 'TRADE_SUCCESS',
            'pay_time': datetime.now().isoformat(),
            'method': payment_method,
            'amount': float(amount)
        }

    @staticmethod
    def refund(order_id, amount):
        """退款"""
        import time
        time.sleep(0.1)

        success = random.random() < 0.9
        if success:
            return {
                'success': True,
                'trade_status': 'REFUND_SUCCESS',
                'refund_no': f"REF{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}",
                'refund_amount': float(amount),
                'refund_time': datetime.now().isoformat()
            }
        else:
            return {
                'success': False,
                'error': '支付系统繁忙，请稍后重试',
                'error_code': 'PAYMENT_SYSTEM_ERROR'
            }

    @staticmethod
    def settlement(order_id, return_time, overdue_days=0, overdue_fee=0, deposit_amount=0):
        """
        归还结算
        计算实际应退还押金金额
        """
        return {
            'success': True,
            'settlement_sn': f"SET{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}",
            'return_time': return_time.isoformat() if hasattr(return_time, 'isoformat') else str(return_time),
            'overdue_days': overdue_days,
            'overdue_fee': float(overdue_fee),
            'deposit_amount': float(deposit_amount),
            'actual_return': float(max(deposit_amount - overdue_fee, 0))
        }

    @staticmethod
    def pay_overdue_debt(order_id, amount):
        """
        支付逾期欠费（模拟）
        """
        import time
        time.sleep(0.1)

        trade_no = f"DEBT{datetime.now().strftime('%Y%m%d%H%M%S')}{random.randint(1000, 9999)}"
        return {
            'success': True,
            'trade_no': trade_no,
            'pay_time': datetime.now().isoformat(),
            'amount': float(amount)
        }
