import asyncio
import base64
import decimal
import json
import os
import time
from typing import Any, Dict, Optional, TYPE_CHECKING, Literal, Union, NewType, Tuple
import urllib.parse

import boto3
from boto3.dynamodb.conditions import Key

if TYPE_CHECKING:
    from mypy_boto3 import dynamodb
else:
    dynamodb = object

LOOP = asyncio.get_event_loop()
EVENT_TABLE_NAME = os.environ["EVENT_TABLE_NAME"]


# Helper class to convert a DynamoDB item to JSON.
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            if o % 1 > 0:
                return float(o)
            else:
                return int(o)
        return super(DecimalEncoder, self).default(o)


def http_resp(status: int, msg: str) -> Any:
    return {"statusCode": status, "body": msg + "\n"}


def log(msg: str) -> None:
    print(msg)


def parse_qs(event) -> Optional[int]:
    qs = urllib.parse.parse_qs(event["rawQueryString"])
    if "ts_day" not in qs:
        return None
    if len(qs["ts_day"]) > 1:
        return None
    ts_day_raw = qs["ts_day"][0]
    ts_day = int(ts_day_raw)
    return ts_day


async def query(event: Dict[str, Any], context: Any) -> Any:
    ts_day = parse_qs(event)
    if ts_day is None:
        return http_resp(400, "Bad ts_day query string arg")
    dynamodb_service_resource: dynamodb.ServiceResource = boto3.resource("dynamodb")
    table = dynamodb_service_resource.Table(EVENT_TABLE_NAME)
    resp: Any = table.query(KeyConditionExpression=Key("ts_day").eq(ts_day))

    print("resp: %r" % resp)

    response = json.dumps(resp["Items"], cls=DecimalEncoder)

    return http_resp(200, response)


def events(event: Any, context: Any) -> Any:
    return LOOP.run_until_complete(query(event, context))
