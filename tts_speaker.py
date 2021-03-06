#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import argparse
import configparser
import logging
import sys
import json
from queue import Queue
import paho.mqtt.client as mqtt
import tenacity
from engine import TTSEngine, Condition

class TTS_Speaker:
    def __init__(self, args, config):
        self.args = args
        self.config = config['BROKER']

        #Thread communication
        self.text_queue = Queue() #Queue for communication between provider and engine
        self.condition = Condition() #Boolean Object to safely stop thread.
        
        #Engine
        self.ttsengine_thread = TTSEngine(self.text_queue, self.condition, self)

        #MQTT broker client
        if args.broker_ip not in ['None', 'none', '']:
            self.broker = self.broker_connect()
        else: 
            self.broker = None

        if self.broker is not None:
            self.broker.subscribe(self.config['broker_topic'])
            self.broker.on_message = self._on_broker_message
 
    def run(self):
        self.ttsengine_thread.start()
        try:
            self.broker.loop_forever()
            self.condition.state = False
        except KeyboardInterrupt:
            logging.info("Process interrupted by user")
        finally:
            self.condition.state = False
            self.text_queue.put('')

    @tenacity.retry(wait=tenacity.wait_fixed(5),
                stop=tenacity.stop_after_attempt(24),
                retry=tenacity.retry_if_result(lambda s: s is None),
                retry_error_callback=(lambda s: s.result())
                )
    def broker_connect(self):
        logging.info("Attempting connexion to broker at %s:%i" % (self.args.broker_ip, self.args.broker_port))
        try:
            broker = mqtt.Client()
            broker.on_connect = self._on_broker_connect
            broker.connect(self.args.broker_ip, self.args.broker_port, 0)

            return broker
        except:
            logging.warning("Failed to connect to broker (Retrying after 5s)")
            return None

    def _on_broker_message(self, client, userdata, message):
        m_string = str(message.payload.decode("utf-8"))
        logging.debug("Received message '%s' from topic %s" % (m_string, message.topic))
        if m_string.find("value") != -1:
            msg = json.loads(m_string)
            self.text_queue.put(msg['value'])
        else:
            self.text_queue.put("Désolé, je n'ai pas compris")
        
    def _on_broker_connect(self, client, userdata, flags, rc):
        logging.info("Connected to broker.")


def main():
    # Logging
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)8s %(asctime)s %(message)s ")
    # Read default config from file
    config = configparser.ConfigParser()
    config.read(os.path.dirname(os.path.abspath(__file__))+"/config.conf")
    default_broker_ip = config['BROKER']['broker_ip']
    default_broker_port = config['BROKER']['broker_port']
    default_broker_topic = config['BROKER']['broker_topic']

    parser = argparse.ArgumentParser(description='Text To Speech Module. Read text from MQTT broker and output it.')
    parser.add_argument('--broker-ip',dest='broker_ip',default=default_broker_ip, help="MQTT Broker IP")
    parser.add_argument('--borker-port', dest='broker_port',default=int(default_broker_port), help='MQTT broker port', type=int)
    parser.add_argument('--broker-topic', dest='broker_topic', default=default_broker_topic, help='Broker on which to publish when the WUW is spotted')
    args = parser.parse_args()
    
    #Instanciate runner
    runner = TTS_Speaker(args, config)
    runner.run()

if __name__ == '__main__':
    main()
