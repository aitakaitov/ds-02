import jsonpickle
import random

import os

from flask_cors import CORS
from flask import Flask, request
from utils import *
import threading
import requests
from datetime import datetime
import argparse

import socket
socket.setdefaulttimeout(5)

PRINT_TO_STD = True
if not PRINT_TO_STD:
    open('output', 'w+', encoding='utf-8').close()

parser = argparse.ArgumentParser()
parser.add_argument('--port', required=True, type=int)
parser.add_argument('--n_nodes', required=True, type=int)
args = vars(parser.parse_args())


TIMEOUT_SEC = 30
#IP_ADDRESS = os.environ['IP_ADDRESS']
#NODE_COUNT = os.environ['NUM_NODES']

PORT = args['port']
IP_ADDRESS = 'localhost'
NODE_COUNT = args['n_nodes']

if PORT != 5001:
    network_info = NetworkInfo(random.randint(0, 2_000_000_000), IP_ADDRESS, NODE_COUNT, PORT)
else:
    network_info = NetworkInfo(2_000_000_000, IP_ADDRESS, NODE_COUNT, PORT)

timers = {}
counters = {}


def create_and_start_timer(func):
    timer = threading.Timer(TIMEOUT_SEC, func)
    timer.start()
    return timer


def send_leader_down_message():
    try:
        if network_info.leader_id != -1:
            return
        log_message(f'Trying to send LEADER DOWN message to the right neighbour')
        response = send_message(BaseRequest(network_info.id, MessageType.LEADER_DOWN))
        log_message(f'Reached the right neighbour')
        timers['leader_down'] = create_and_start_timer(send_leader_down_message)
    except BaseException:
        timers['leader_down'] = create_and_start_timer(send_leader_down_message)


def send_election_message():
    try:
        if counters['election_init'] * TIMEOUT_SEC >= 720:
            log_message('Could not contact the right neighbour for 10 minutes, assuming dead and moving onto next one')
            network_info.next_neighbour_shift()
            log_message(f'New right neighbour: {network_info.get_right_neighbour_address()}')

        log_message(f'Trying to send an election message to the right neighbour')
        response = send_message(BaseRequest(network_info.id, MessageType.ELECTION_ROUND))
        network_info.right_neighbour_id = response.json()['id']
        log_message(f'Reached the right neighbour')

        # Now that we know our right neighbour is alive, we can start pinging him
        timers['ping'] = create_and_start_timer(ping_right_neighbour)
        counters['election_init'] = 0

        if not network_info.round_trip_made:
            timers['election_init'] = create_and_start_timer(send_election_message)

    except BaseException:
        log_message(f'Could not contact the neighbour, retry in {TIMEOUT_SEC} seconds')
        timers['election_init'] = create_and_start_timer(send_election_message)
        counters['election_init'] += 1


timers['election_init'] = create_and_start_timer(send_election_message)
counters['election_init'] = 0

def recover_neighbour_dead():
    leader_dead = network_info.right_neighbour_id == network_info.leader_id
    neighbour_reachable = False
    while not neighbour_reachable:
        valid = network_info.next_neighbour_shift()
        if not valid:
            log_message('Only one node left in the ring, setting as leader and coloring GREEN')
            network_info.leader_id = network_info.id
            network_info.color = Color.GREEN
            return

        # try to contact the next in ring - if it does
        log_message(f'Setting right neighbour to {network_info.get_right_neighbour_address()}, contacting')
        try:
            response = send_message(BaseRequest(network_info.id, MessageType.PING))
            network_info.right_neighbour_id = response.json()['id']
            neighbour_reachable = True
        except BaseException:
            log_message(f'Could not contact {network_info.right_neighbour_ip}')

    if leader_dead:
        # if the leader is down, we send a message to inform others that the leader is down - this message
        # should be able to make it's way around the ring setting everyone's leader IDs to -1, allowing for the election
        # process to take place
        network_info.leader_id = -1
        #send_message(BaseRequest(network_info.id, MessageType.LEADER_DOWN))

        # then we periodically send election messages - this is done in order to make sure that no one blocks the
        # election message because their leader ID is not -1 yet (possible with threaded servers)
        #timers['election_init'] = create_and_start_timer(send_election_message)
        timers['leader_down'] = create_and_start_timer(send_leader_down_message)
    else:
        # if the node is not the leader, we just send a message announcing it around and the leader catches it
        # he will then collect IDs again and color the ring
        if network_info.leader_id == network_info.id:
            send_message(BaseRequest(network_info.id, MessageType.NODE_DOWN), this_address=True)
        else:
            send_message(BaseRequest(network_info.id, MessageType.NODE_DOWN))

    if not timers['ping'].is_alive():
        timers['ping'] = create_and_start_timer(ping_right_neighbour)


def ping_right_neighbour():
    try:
        log_message(f'Pinging right neighbour')
        send_message(BaseRequest(network_info.id, MessageType.PING))
        log_message(f'Right neighbour responded')

        timers['ping'] = create_and_start_timer(ping_right_neighbour)

    except BaseException:
        log_message(f'Could not contact the neighbour, assuming dead, attempting to recover')
        recover_neighbour_dead()


# --------------------------------------------------------------------------------------------------
# Utility functions
# --------------------------------------------------------------------------------------------------


def send_message(message, this_address=False):
    return requests.post(
        network_info.get_right_neighbour_address() if not this_address else network_info.get_this_address(),
        jsonpickle.encode(message, keys=True)
    )


def forward_message(message):
    try:
        message.sender_id = network_info.id
        send_message(message)
    except BaseException:
        log_message(f'Could not forward message')


def sender_this_node(message):
    return message.original_id == network_info.id


def log_message(string):
    if PRINT_TO_STD:
        print(f'[{datetime.utcnow()}][{network_info.id}]\t{string}')
    else:
        with open('output', 'a', encoding='utf-8') as f:
            print(f'[{datetime.utcnow()}][{network_info.id}]\t{string}', file=f, flush=True)

# --------------------------------------------------------------------------------------------------
# FLASK needs to be at the bottom since we need to do some things before it blocks on the run() call
# --------------------------------------------------------------------------------------------------


log_message(f'Node {network_info.id} starting up')
#log_message(f'Node IP: {network_info.ip}\nNeighbour IP: {network_info.right_neighbour_ip}\nNumber of nodes: {network_info.node_count}')
log_message(f'Node IP: {network_info.ip}:{network_info.port}\nNeighbour IP: {network_info.get_right_neighbour_address()}\nNumber of nodes: {network_info.node_count}')
app = Flask(__name__)


# TODO detect errors in message sending and initiate recovery


@app.route('/message', methods=['POST'])
def process_message():
    data = jsonpickle.decode(request.data, keys=True)

    # simply reply to pings
    if data.message_type == MessageType.PING:
        return '{ "id": ' + f'{network_info.id}' + '}', 200

    # the leader is down and we prepare for a new election
    elif data.message_type == MessageType.LEADER_DOWN:
        network_info.leader_down = True
        # if we have not sent this message, just forward it and set leader ID to -1
        if not sender_this_node(data):
            log_message('Received LEADER DOWN message, forwarding')
            network_info.leader_id = -1
            forward_message(data)
        # If we have sent this message, we stop sending them and we start sending election messages
        else:
            if 'leader_down' in timers.keys():
                timers['leader_down'].cancel()
                timers['election_init'] = create_and_start_timer(send_election_message())
        return '{ "id": ' + f'{network_info.id}' + '}', 200

    # a node in the ring went down
    elif data.message_type == MessageType.NODE_DOWN:
        # if we are not the leader, we just forward the message
        if not network_info.id == network_info.leader_id:
            log_message('Received NODE DOWN message, forwarding')
            forward_message(data)
            return '{ "id": ' + f'{network_info.id}' + '}', 200
        # otherwise, we start ID collection, which naturally leads to recoloring
        else:
            log_message('Received NODE DOWN message, starting new ID COLLECTION')
            send_message(CollectRequest(network_info.id))
            return '{ "id": ' + f'{network_info.id}' + '}', 200

    # if the election is ongoing
    elif data.message_type == MessageType.ELECTION_ROUND:
        # ignore if leader is already elected
        if network_info.leader_id != -1:
            return '{ "id": ' + f'{network_info.id}' + '}', 201
        # block messages with lower id
        if data.original_id < network_info.id:
            # if the leader is down, repeat the message
            if network_info.leader_down:
                send_message(BaseRequest(network_info.id, MessageType.ELECTION_ROUND))
            log_message(f'Received election message with lower ID, blocking')
            return '{ "id": ' + f'{network_info.id}' + '}', 200
        # this node is the leader
        elif sender_this_node(data):
            # this is here because of repeat messages
            if network_info.leader_id == -1:
                # stop sending election messages
                timers['election_init'].cancel()
                network_info.round_trip_made = True
                # announce leader
                log_message(f'Election message came back to origin, announcing as leader')
                send_message(BaseRequest(network_info.id, MessageType.LEADER_ELECTED))
                network_info.leader_id = network_info.id

            return '{ "id": ' + f'{network_info.id}' + '}', 200
        # forward the message
        else:
            forward_message(data)
            return '{ "id": ' + f'{network_info.id}' + '}', 200

    # register the elected leader
    elif data.message_type == MessageType.LEADER_ELECTED:
        # leader is elected, we don't need to send election messages
        timers['election_init'].cancel()
        network_info.round_trip_made = True
        network_info.leader_down = False

        log_message(f'Leader elected message received')
        network_info.leader_id = data.original_id

        # if the message returns back to the leader
        # send a message to collect IDs
        if sender_this_node(data):
            log_message(f'Leader elected message came back to leader')
            log_message(f'Sending collection message')
            send_message(CollectRequest(network_info.id))
        else:
            forward_message(data)

        return '{ "id": ' + f'{network_info.id}' + '}', 200

    # round trip ids collect message
    elif data.message_type == MessageType.COLLECT_IDS:
        # if the message came back
        if sender_this_node(data):
            log_message(f'Collection message came back to origin')
            network_info.node_ids = data.ids
            log_message(f'Color set to GREEN')
            log_message(f'Sending coloring request')
            color_request = ColorRequest(network_info.id, network_info.node_ids)
            send_message(color_request)
            pass
        # add node ID and pass message
        else:
            log_message(f'Adding ID to the collection message')
            data.ids.append(network_info.id)
            send_message(data)

        return '{ "id": ' + f'{network_info.id}' + '}', 200

    # coloring message
    elif data.message_type == MessageType.COLORING:
        # message came back
        if sender_this_node(data):
            log_message('Coloring request came back to origin')
            log_message('Colors are all set')
            log_message(f'\nNode ID\tColor\n' + '\n'.join(f'{node}\t {color}' for node, color in data.node_color_dict.
                                                          items()))
        # this node is getting colored
        else:
            log_message(f'Setting color to {data.node_color_dict[network_info.id]}')
            network_info.color = data.node_color_dict[network_info.id]
            forward_message(data)

        return '{ "id": ' + f'{network_info.id}' + '}', 200


CORS(app)
#app.run('0.0.0.0')
app.run(host='localhost', port=PORT)