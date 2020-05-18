# DCSS Central Event Store

## Architecture

### Event Submission

Inbound events are sent in from DCSS online servers to a `/submit` HTTPS endpoint with the following body:

```json
{
  "type": "milestone",
  "src": "cpo",
  "data": {
    "v": "0.25-a0",
    // ...
    "name": "edsrzf",
    "race": "Deep Elf",
    // ...
    "time": "20200418093334S",
    "milestone": "killed Blork the orc."
  }
}
```

This is stored in a DynamoDB table, partitioned by day with a (unique) sort key of the millisecond the event was accepted.

This is an authenticated endpoint.

### Event Reading

Current API design is not final. It's simplest possible implementation.

GET requests to `/events?ts_day=N` will return all events submitted on the day specified by `ts_day`. `ts_day` is the millisecond at the start of the day. You can calculate today's `ts_day` with this Python command:

```sh
python -c 'import time; now = time.time(); print(int(now / 86_400) * 86_400)'
```

There is no authentication for this endpoint.

### Security

POSTs to `/submit` need an `Authorization` header with a valid key. Keys are stored in a secondary DynamoDB table and limited to submitting data for a single `src`. They are manually managed.

GETs to `/event` are unauthenticated.

API routes will be protected by throttling. Exact implementation TBD.

### AWS Infrastructure costs

API Gateway (HTTP API) -> Submit / Events Lambda -> Key / Events DynamoDB table

Also CloudWatch Logs data written.

Current activity level is ~23k milestones per day and ~3.5k logfiles. Average size is 500bytes/milestone and 600bytes/log. Or 10mb + 2mb = 12mb traffic per day. This rounds to $0/mo.

Read data is harder to estimate. Assuming 50 active clients reading events in realtime (1 event per request) is 1.5mil events per day.
HTTP API $0.03/day
Lambda (300ms/128mb/invocation) = $0.006 for requests + $0.02 for duration / day
DynamoDB (0.75m reads) $0.005 / day
TOTAL ~ $1.8/client/month

## Quickstart

1. Install serverless

    ```sh
    npm install
    ```

2. Deploy stack

    ```sh
    npx serverless deploy
    ```

3. Add an API key to the KeyTable (you can find the table name in the AWS DynamoDB web console)

    ```sh
    aws dynamodb put-item \
      --table-name "dcss-central-event-store-dev-KeyTable-xxx" \
      --item '{"key": {"S": "qwerty"}, "src": {"S": "cpo"}}'

4. Add an event via the `/submit` POST endpoint (found in output of `serverless deploy` command)

    ```sh
    curl -v \
      -H 'Authorization: qwerty' \
      --data @test-event-body.json \
      $submit_url
    ```

    You'll get an empty body HTTP 204 back on success.

    You can run this request a few times to add multiple items to the table.

5. Get events via the `/events` GET endpoint (found in output of `serverless deploy` command). Get the correct value for `ts_day` by checking the items in the events table via the AWS web console.

    ```sh
    curl -v \
      "$events_url?ts_day=1589760000000"
    ```

    You'll get a JSON array of all the items you submitted in the previous step (assuming it's still the same  UTC day).

6. Tear down all infra.

    ```sh
    npx serverless remove
    ```

## Questions

**Q: How are events uniquely identified.**

A: By millisecond of submission to this service.

**Q: The millisecond of event submission is not unique.**

A: We only accept one event per millisecond. If two events are submitted at the same time, one will fail to be put into the DynamoDB database. The API will internally retry until success or a failure limit is reached.

(Implementation of this is TODO. Requires `ConditionExpression` implementation on `PutItem` call.)

**Q: How do I test locally.**

A: Testing with live DynamoDB but local Lambda emulation:

```sh
npx serverless invoke local -f submit -p test-event.json -e TABLE_NAME=xxx
```

```sh
npx serverless invoke local -f events -e TABLE_NAME=xxx
```

DynamoDB local emulation requires a Docker container. Not included in this repo yet.
