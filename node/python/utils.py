import math
from enum import Enum

GREEN_COLOR_FRACTION = 1 / 3
IP_OFFSET = 100


class NetworkInfo:
    def __init__(self, _id, ip, node_count):
        self.id = _id
        self.node_count = int(node_count)
        self.ip = ip
        self.leader_id = -1
        self.color = None
        self.node_ids = None

        self.round_trip_made = False

        split_ip = ip.split('.')
        self.ip_prefix = split_ip[0] + '.' + split_ip[1] + '.' + split_ip[2]
        this = int(split_ip[3])

        # One to the right if we are not the last node, otherwise the first node
        if self.node_count == 2:
            _next = 1 if this % 2 == 0 else 2
        else:
            _next = this + 1 if this - IP_OFFSET != self.node_count else IP_OFFSET + 1

        self.right_neighbour_ip = f'{self.ip_prefix}.{_next}'

        self.right_neighbour_id = -1

    def get_right_neighbour_address(self):
        return f'http://{self.right_neighbour_ip}:5000/message'

    def next_neighbour_shift(self):
        split_ip = self.right_neighbour_ip.split('.')
        neighbour = int(split_ip[3])

        if self.node_count == 2:
            # With two nodes we can't really shift anymore
            return False
        else:
            _next = neighbour + 1 if neighbour - IP_OFFSET != self.node_count else IP_OFFSET + 1

        self.right_neighbour_ip = f'{self.ip_prefix}.{_next}'
        return True


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
