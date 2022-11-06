import jsonpickle
import random
import os
from flask_cors import CORS
from flask import Flask, request
from utils import *
import requests
from datetime import datetime
import argparse
import threading

import socket
socket.setdefaulttimeout(5)

PRINT_TO_STD = True
if not PRINT_TO_STD:
    open('output', 'w+', encoding='utf-8').close()

MODE = 'port'
TIMEOUT_SEC = 30

if MODE == 'port':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', required=True, type=int)
    parser.add_argument('--n_nodes', required=True, type=int)
    args = vars(parser.parse_args())
    PORT = args['port']
    IP_ADDRESS = 'localhost'
    NODE_COUNT = args['n_nodes']
elif MODE == 'ip':
    IP_ADDRESS = os.environ['IP_ADDRESS']
    NODE_COUNT = os.environ['NUM_NODES']
    PORT = 5000


#if PORT != 5001:
network_info = NetworkInfo(random.randint(0, 2_000_000_000), IP_ADDRESS, NODE_COUNT, PORT, MODE)
#else:
#    network_info = NetworkInfo(2_000_000_000, IP_ADDRESS, NODE_COUNT, PORT)

timer_manager = TimerManager(TIMEOUT_SEC)
counters = {}


def send_leader_down_message():
    try:
        if network_info.leader_id != -1:
            return
        log_message(f'Sending LEADER_DOWN to the right neighbour')
        response = send_message(BaseRequest(network_info.id, MessageType.LEADER_DOWN))
        log_message(f'OK sending LEADER_DOWN to the right neighbour')
    except BaseException:
        log_message('FAIL sending LEADER_DOWN to the right neighbour')

    timer_manager.add_timer_and_run('leader_down', send_leader_down_message)


def send_election_message():
    try:
        if counters['election_init'] * TIMEOUT_SEC >= 720:
            log_message('Could not contact the right neighbour for 10 minutes, assuming dead and moving onto next one')
            network_info.next_neighbour_shift()
            log_message(f'New right neighbour: {network_info.get_right_neighbour_address()}')

        log_message(f'Sending ELECTION to the right neighbour')
        response = send_message(BaseRequest(network_info.id, MessageType.ELECTION_ROUND))
        network_info.right_neighbour_id = response.json()['id']
        log_message(f'OK sending ELECTION to the right neighbour')

        # Now that we know our right neighbour is alive, we can start pinging him
        exists = timer_manager.add_run_if_not_existing('ping', ping_right_neighbour)
        if exists:
            log_message('-- starting ping in send_election_message')
        counters['election_init'] = 0

        if not network_info.round_trip_made:
            timer_manager.add_timer_and_run('election_init', send_election_message)
            log_message('-- round trip not made yet, continue sending ELECTION messages')

    except BaseException:
        log_message(f'FAIL sending ELECTION to the right neighbour')
        timer_manager.add_timer_and_run('election_init', send_election_message)
        log_message('-- continue sending ELECTION messages')
        counters['election_init'] += 1


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
            timer_manager.add_timer_and_run('ping', ping_right_neighbour)
            log_message('-- starting pinging after neighbour reached')
        except BaseException:
            log_message(f'Could not contact {network_info.right_neighbour_ip}')

    if leader_dead:
        # if the leader is down, we send a message to inform others that the leader is down - this message
        # should be able to make it's way around the ring setting everyone's leader IDs to -1, allowing for the election
        # process to take place
        network_info.leader_id = -1

        # then we periodically send election messages - this is done in order to make sure that no one blocks the
        # election message because their leader ID is not -1 yet (possible with threaded servers)
        timer_manager.add_timer_and_run('leader_down', send_leader_down_message)
        log_message('-- started leader down timer')
    else:
        # if the node is not the leader, we just send a message announcing it around and the leader catches it
        # he will then collect IDs again and color the ring
        if network_info.leader_id == network_info.id:
            log_message('Sending NODE_DOWN message to SELF')
            send_message(BaseRequest(network_info.id, MessageType.NODE_DOWN), this_address=True)
        else:
            log_message('Sending NODE_DOWN message to the right neighbour')
            send_message(BaseRequest(network_info.id, MessageType.NODE_DOWN))


def ping_right_neighbour():
    try:
        log_message(f'Pinging right neighbour {network_info.right_neighbour_ip}')
        send_message(BaseRequest(network_info.id, MessageType.PING))
        log_message(f'Right neighbour responded to ping')

        timer_manager.cancel_timer('ping')
        timer_manager.add_timer_and_run('ping', ping_right_neighbour)
        log_message('-- starting ping in ping_right_neighbour')
    except BaseException:
        timer_manager.cancel_timer('ping')
        log_message(f'Could not ping the neighbour, assuming dead, attempting to recover')
        recover_neighbour_dead()


def send_message_async(message, this_address=False):
    thread = threading.Thread(target=send_message, args=(message, this_address))
    thread.start()


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
        log_message(f'Could not forward message \n{message}')


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
log_message(f'Node IP: {network_info.ip}:{network_info.port}\nNeighbour IP: {network_info.get_right_neighbour_address()}\nNumber of nodes: {network_info.node_count}')

timer_manager.add_timer_and_run('election_init', send_election_message)
log_message('-- starting ELECTION timer')
counters['election_init'] = 0

app = Flask(__name__)

import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)


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
            log_message('LEADER DOWN received, forwarding')
            network_info.leader_id = -1
            forward_message(data)
        # If we have sent this message, we stop sending them and we start sending election messages
        else:
            network_info.leader_down = False
            log_message('LEADER DOWN received at origin')
            log_message('-- cancelling leader down timer')
            timer_manager.cancel_timer('leader_down')
            log_message('-- starting election timer')
            if timer_manager.check_timer_exists('leader_down'):
                timer_manager.add_timer_and_run('election_init', send_election_message)
            else:
                log_message('-- leader down timer did not exist, election timer was not started')

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
            log_message('Ignoring ELECTION message as leader exists')
            return '{ "id": ' + f'{network_info.id}' + '}', 201
        # block messages with lower id
        if data.original_id < network_info.id:
            # if the leader is down, repeat the message
            if network_info.leader_down:
                log_message('Received ELECTION message with lower ID, propagating my own as leader is down')
                send_message(BaseRequest(network_info.id, MessageType.ELECTION_ROUND))
            else:
                log_message(f'Received ELECTION message with lower ID, blocking')
            return '{ "id": ' + f'{network_info.id}' + '}', 200
        # this node is the leader
        elif sender_this_node(data):
            # this is here because of repeat messages
            if network_info.leader_id == -1:
                # stop sending election messages
                log_message('-- cancelling election timer')
                timer_manager.cancel_timer('election_init')
                network_info.round_trip_made = True
                # announce leader
                log_message(f'ELECTION message came back to origin, announcing as leader')
                send_message(BaseRequest(network_info.id, MessageType.LEADER_ELECTED))
                network_info.leader_id = network_info.id

            return '{ "id": ' + f'{network_info.id}' + '}', 200
        # forward the message
        else:
            log_message('Forwarding ELECTION message')
            forward_message(data)
            return '{ "id": ' + f'{network_info.id}' + '}', 200

    # register the elected leader
    elif data.message_type == MessageType.LEADER_ELECTED:
        log_message(f'LEADER_ELECTED message received')
        # leader is elected, we don't need to send election messages
        timer_manager.cancel_timer('election_init')
        log_message('-- election timer stopped as leader was elected')

        exists = timer_manager.add_run_if_not_existing('ping', ping_right_neighbour)
        if not exists:
            log_message('-- starting ping in leader_elected')

        network_info.round_trip_made = True
        network_info.leader_down = False

        log_message(f'Setting leader ID')
        network_info.leader_id = data.original_id

        # if the message returns back to the leader
        # send a message to collect IDs
        if sender_this_node(data):
            log_message(f'LEADER ELECTED message came back to leader')
            log_message(f'Sending COLLECTION message')
            send_message(CollectRequest(network_info.id))
        else:
            log_message('Forwarding LEADER_ELECTED message')
            forward_message(data)

        return '{ "id": ' + f'{network_info.id}' + '}', 200

    # round trip ids collect message
    elif data.message_type == MessageType.COLLECT_IDS:
        # if the message came back
        if sender_this_node(data):
            log_message(f'COLLECTION message came back to origin')
            network_info.node_ids = data.ids
            log_message(f'Color set to Color.GREEN')
            log_message(f'Sending COLORING request')
            color_request = ColorRequest(network_info.id, network_info.node_ids)
            send_message(color_request)
            pass
        # add node ID and pass message
        else:
            log_message(f'Adding ID to the COLLECTION message')
            data.ids.append(network_info.id)
            send_message(data)

        return '{ "id": ' + f'{network_info.id}' + '}', 200

    # coloring message
    elif data.message_type == MessageType.COLORING:
        # message came back
        if sender_this_node(data):
            log_message('COLORING request came back to origin')
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

if MODE == 'port':
    app.run(host='localhost', port=PORT)
elif MODE == 'ip':
    app.run(host='0.0.0.0', port=PORT)
