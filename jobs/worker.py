
import json
import logging
import os
import time

import pika

from metadata.repair import repair_chunks

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("repair-worker")

RABBITMQ_URL = os.getenv(
    "RABBITMQ_URL",
    "amqp://guest:guest@rabbitmq:5672/"
)

QUEUE_NAME = "storage_repair_jobs"


def connect():
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.URLParameters(RABBITMQ_URL)
            )
            return connection

        except pika.exceptions.AMQPConnectionError:
            logger.warning(
                "RabbitMQ unavailable, retrying..."
            )
            time.sleep(5)


def main():
    while True:
        connection = connect()

        try:
            channel = connection.channel()

            channel.queue_declare(
                queue=QUEUE_NAME,
                durable=True
            )

            channel.basic_qos(prefetch_count=1)

            def process_job(
                channel,
                method,
                properties,
                body
            ):
                try:
                    job = json.loads(body)
                    job_type = job.get("type")

                    logger.info(
                        "Received job: %s",
                        job
                    )

                    if job_type == "repair":
                        result = repair_chunks()

                    else:
                        logger.warning(
                            "Unsupported job: %s",
                            job_type
                        )

                        channel.basic_ack(
                            delivery_tag=method.delivery_tag
                        )
                        return

                    logger.info(
                        "JOB COMPLETED id=%s result=%s",
                        job.get("job_id"),
                        result
                    )

                    channel.basic_ack(
                        delivery_tag=method.delivery_tag
                    )

                except Exception:
                    logger.exception(
                        "Job execution failed"
                    )

                    # Requeue failed jobs for another attempt.
                    channel.basic_nack(
                        delivery_tag=method.delivery_tag,
                        requeue=True
                    )

                    time.sleep(2)

            channel.basic_consume(
                queue=QUEUE_NAME,
                on_message_callback=process_job
            )

            logger.info(
                "Repair worker ready. Waiting for jobs."
            )

            channel.start_consuming()

        except Exception:
            logger.exception(
                "Worker connection failed"
            )
            time.sleep(5)

        finally:
            if connection.is_open:
                connection.close()


if __name__ == "__main__":
    main()
