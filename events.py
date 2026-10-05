"""The event stream as described in the requirements in the same order. `day` is  booked day."""
from decimal import Decimal as D

ACCOUNTS = [("ACC-001", "AED"), ("ACC-002", "BHD")]

EVENTS = [
    {"id": "E1",  "day": 1, "type": "CREDIT",        "account": "ACC-001", "amount": D("1200.00"), "value_day": 1},
    {"id": "E2",  "day": 1, "type": "DEBIT",         "account": "ACC-001", "amount": D("950.00"),  "value_day": 1},
    {"id": "E3",  "day": 2, "type": "AUTHORIZATION", "account": "ACC-001", "auth_id": "Auth-A", "amount": D("200.00"), "value_day": 2},
    {"id": "E4",  "day": 3, "type": "CREDIT",        "account": "ACC-001", "amount": D("400.00"),  "value_day": 3},
    {"id": "E5",  "day": 4, "type": "SETTLEMENT",    "account": "ACC-001", "auth_id": "Auth-A", "amount": D("185.00"), "value_day": 4},
    {"id": "E6",  "day": 4, "type": "SETTLEMENT",    "account": "ACC-001", "auth_id": "Auth-Z", "amount": D("180.00"), "value_day": 4},
    {"id": "E7",  "day": 5, "type": "DEBIT",         "account": "ACC-001", "amount": D("620.00"),  "value_day": 2},
    {"id": "E8",  "day": 5, "type": "AUTHORIZATION", "account": "ACC-001", "auth_id": "Auth-B", "amount": D("90.00"),  "value_day": 5},
    {"id": "E9",  "day": 6, "type": "REVERSAL",      "account": "ACC-001", "target": "E7", "value_day": 2},
    {"id": "E10", "day": 5, "type": "CREDIT_INSTALMENTS", "account": "ACC-002", "amount": D("10.000"), "instalments": 3, "value_day": 5},
]
