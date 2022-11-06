import math
import threading
from enum import Enum

GREEN_COLOR_FRACTION = 1 / 3
IP_OFFSET = 100


class NetworkInfo:
    def __init__(self, _id, ip, node_count, port, mode):
        # this node ID
        self.id = _id
        self.node_count = int(node_count)
        # this node IP
        self.ip = ip
        self.leader_id = -1
        self.color = None
        # only used by leader
        self.node_ids = None
        # the port we run on
        self.port = port

        # if a message has made a full circle
        self.round_trip_made = False
        # if the leader is down
        self.leader_down = False
        self.mode = mode

        if mode == 'ip':
            split_ip = ip.split('.')
            self.ip_prefix = split_ip[0] + '.' + split_ip[1] + '.' + split_ip[2]
            this = int(split_ip[3])

            # One to the right if we are not the last node, otherwise the first node
            if self.node_count == 2:
                _next = 1 if this % 2 == 0 else 2
            else:
                _next = this + 1 if this - IP_OFFSET != self.node_count else IP_OFFSET + 1
            self.right_neighbour_ip = f'{self.ip_prefix}.{_next}'
            self.right_neighbour_port = port

        elif mode == 'port':
            _next = port + 1 if port - 5000 != self.node_count else 5000 + 1
            self.right_neighbour_ip = f'{self.ip}'
            self.right_neighbour_port = _next

        self.right_neighbour_id = -1

    def get_right_neighbour_address(self):
        return f'http://{self.right_neighbour_ip}:{self.right_neighbour_port}/message'

    def get_this_address(self):
        return f'http://{self.ip}:{self.port}/message'

    def next_neighbour_shift(self):
        if self.mode == 'ip':
            split_ip = self.right_neighbour_ip.split('.')
            neighbour = int(split_ip[3])

            if self.node_count == 2:
                # With two nodes we can't really shift anymore
                return False
            else:
                _next = neighbour + 1 if neighbour - IP_OFFSET != self.node_count else IP_OFFSET + 1

            self.right_neighbour_ip = f'{self.ip_prefix}.{_next}'
            return self.right_neighbour_ip != self.ip
        elif self.mode == 'port':
            self.right_neighbour_port = self.right_neighbour_port + 1 if self.right_neighbour_port - 5000 != self.node_count else 5000 + 1
            return self.right_neighbour_port != self.port


class TimerManager:
    def __init__(self, timeout):
        self.timers = {}
        self.timeout = timeout
        self.lock = threading.RLock()

    def add_timer_and_run(self, key, func, purge=False):
        """
        Adds a timer and runs it
        :param key: timer key
        :param func: timer function
        :param purge: by default if a timer with the key exists and does not have Timer.finished set
        it is not overwritten and a new timer is not started. Setting purge to True overrides this behaviour
        :return:
        """
        self.lock.acquire()
        if key in self.timers.keys():
            if not self.timers[key].finished.is_set() and not purge:
                self.lock.release()
                return
            else:
                self.timers[key] = threading.Timer(self.timeout, func)
                self.timers[key].start()
        else:
            self.timers[key] = threading.Timer(self.timeout, func)
            self.timers[key].start()
        self.lock.release()

    def cancel_timer(self, key):
        self.lock.acquire()
        if key in self.timers.keys():
            self.timers[key].cancel()
        self.lock.release()

    def check_timer_exists(self, key):
        self.lock.acquire()
        exists = key in self.timers.keys()
        self.lock.release()
        return exists

    def add_run_if_not_existing(self, key, func):
        self.lock.acquire()
        exists = self.check_timer_exists(key)
        if not exists:
            self.add_timer_and_run(key, func)
        self.lock.release()
        return exists


class BaseRequest:
    def __init__(self, original_id, message_type=None):
        self.original_id = original_id
        self.sender_id = original_id
        self.message_type = message_type


class CollectRequest(BaseRequest):
    def __init__(self, original_id):
        super(CollectRequest, self).__init__(original_id, MessageType.COLLECT_IDS)
        self.ids = [original_id]


class ColorRequest(BaseRequest):
    def __init__(self, original_id, all_node_ids):
        super(ColorRequest, self).__init__(original_id, MessageType.COLORING)
        self.node_color_dict = {}
        self.__determine_coloring(all_node_ids)

    def __determine_coloring(self, all_node_ids):
        node_count = len(all_node_ids)
        green_node_count = math.ceil(node_count * GREEN_COLOR_FRACTION)
        green_nodes = all_node_ids[:green_node_count]
        red_nodes = all_node_ids[green_node_count:]

        for green_node in green_nodes:
            self.node_color_dict[green_node] = Color.GREEN
        for red_node in red_nodes:
            self.node_color_dict[red_node] = Color.RED


class BaseResponse:
    def __init__(self, _id):
        self.id = _id


class Color(Enum):
    RED = 'red',
    GREEN = 'green'


class MessageType(Enum):
    # Health-check ping
    PING = 'ping',
    # Pass node's ID around in the election process
    ELECTION_ROUND = 'election_round'
    # Notify nodes that leader has been elected
    LEADER_ELECTED = 'leader_elected',
    # Collect IDs
    COLLECT_IDS = 'collect_ids',
    # Coloring info
    COLORING = 'coloring',
    # Notify a node that another node is down
    NODE_DOWN = 'node_down',
    # If the node that went down is the leader and a new election has to start
    LEADER_DOWN = 'leader_down'
