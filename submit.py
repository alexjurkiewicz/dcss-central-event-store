import asyncio
import base64
import decimal
import json
import os
import time
from typing import Any, Dict, Optional, TYPE_CHECKING, Literal, Union, NewType, Tuple

import boto3

if TYPE_CHECKING:
    from mypy_boto3 import dynamodb
else:
    dynamodb = object

LOOP = asyncio.get_event_loop()
EVENT_TABLE_NAME = os.environ["EVENT_TABLE_NAME"]
KEY_TABLE_NAME = os.environ["KEY_TABLE_NAME"]

DYNAMODB: "dynamodb.ServiceResource" = boto3.resource("dynamodb")
EVENT_TABLE = DYNAMODB.Table(EVENT_TABLE_NAME)
KEY_TABLE = DYNAMODB.Table(KEY_TABLE_NAME)

ValidationSuccess = NewType("ValidationSuccess", Tuple[Literal[True], str])  # src
ValidationFailure = NewType("ValidationFailure", Tuple[Literal[False], str])  # reason
ValidationResult = Union[ValidationSuccess, ValidationFailure]

ParseSuccess = NewType("ParseSuccess", Tuple[Literal[True], Any])  # body
ParseFailure = NewType("ParseFailure", Tuple[Literal[False], str])  # reason
ParseResult = Union[ParseSuccess, ParseFailure]


def http_resp(status: int, msg: str) -> Any:
    return {"statusCode": status, "body": msg + "\n"}


def log(msg: str) -> None:
    print(msg)


def validate_request(event: Dict[str, Any]) -> ValidationResult:
    auth = event["headers"].get("authorization")
    if auth is None:
        return ValidationFailure((False, "No Authorization header"))

    # Override type -- the return type in mypy_boto3 is incomplete
    resp = KEY_TABLE.get_item(Key={"key": auth}, ConsistentRead=False)  # type: Any
    src = resp["Item"].get("src")
    if src is None:
        return ValidationFailure((False, "Not authorized to submit events for any src"))
    return ValidationSuccess((True, src))


def parse_body(event: Any) -> ParseResult:
    body_raw = event.get("body")
    if not body_raw:
        return ParseFailure((False, "Missing event body"))
    if event["isBase64Encoded"]:
        body_raw = base64.b64decode(body_raw)
    try:
        body = json.loads(body_raw)
    except json.decoder.JSONDecodeError as e:
        return ParseFailure((False, "Couldn't decode JSON (%s)" % e))
    return ParseSuccess((True, body))


async def submit(event: Dict[str, Any], context: Any) -> Any:
    log("Processing event %r" % json.dumps(event))
    validation_result = validate_request(event)
    if validation_result[0] == False:
        return http_resp(400, validation_result[1])
    src = validation_result[1]

    body_result = parse_body(event)
    if body_result[0] == False:
        return http_resp(400, body_result[1])
    body = body_result[1]
    if src != body["src"]:
        return http_resp(400, "Unauthorized src")

    log("Submitting body %r" % body)

    now = time.time()
    ts_day = int(now - (now % 86_400)) * 1000
    ts = int(now * 1000)

    # Override type -- the return type in mypy_boto3 is incomplete
    resp: Any = EVENT_TABLE.put_item(
        Item={
            "ts_day": ts_day,
            "ts": ts,
            "type": body["type"],
            "src": src,
            "data": body["data"],
        }
    )
    if resp["ResponseMetadata"]["HTTPStatusCode"] == 200:
        log("resp: %s" % json.dumps(resp))
        return http_resp(202, "")
    else:
        log("failed resp: %s" % json.dumps(resp))
        return http_resp(500, "Internal Error")


def handler(event: Any, context: Any) -> Any:
    return LOOP.run_until_complete(submit(event, context))
