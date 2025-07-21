import zmq
import json
import uuid
import time
import numpy as np
from enum import Enum
from threading import Thread, current_thread

from openephysobj import OpenEphysEventObject, OpenEphysSpikeObject
from pythonosc import udp_client

# create class DataManager to store data using circular buffer and np.ndarray
class DataManager:
    def __init__(self):
        self.channels = []
        self.buffer_size = 300000 # 10 Seconds of data at 30kHz sample rate
        self.lowest_tail_index = 0  # Track the lowest tail index across all channels

    def init_empty_buffer(self, num_channels, num_samples):
        """Initialize an empty buffer for a given number of channels and samples."""
        if num_channels <= 0 or num_samples <= 0:
            raise ValueError("Number of channels and samples must be positive integers.")
        self.channels = [{
            "id": i,
            "label": "",
            "head_sample_number": 0,
            "tail_index": 0,
            "tail_sample_number": 0,
            # 1D buffer for each channel
            "data": np.zeros(self.buffer_size, dtype=np.float32)
        } for i in range(num_channels)]
        print(f"Initialized empty buffer with {num_channels} channels and {num_samples} samples per channel.")


    def push_data(self, channel_id, data):
        """Add data to the buffer for a given channel. Data must be 1D (samples,)"""
        if channel_id < 0 or channel_id >= len(self.channels):
            raise ValueError("Invalid channel ID.")
        channel = self.channels[channel_id]
        tail_index = channel['tail_index']
        # Flatten data in case it's 2D (e.g., (1, N))
        data = np.asarray(data).flatten()
        num_samples = data.shape[0]
        if num_samples > self.buffer_size:
            raise ValueError("Data exceeds buffer size.")
        # Handle wrap-around for circular buffer
        end_index = tail_index + num_samples
        if end_index <= self.buffer_size:
            channel['data'][tail_index:end_index] = data
        else:
            first_part = self.buffer_size - tail_index
            channel['data'][tail_index:] = data[:first_part]
            channel['data'][:end_index % self.buffer_size] = data[first_part:]
        # Update tail index and head sample number
        channel['tail_index'] = (tail_index + num_samples) % self.buffer_size
        channel['tail_sample_number'] += num_samples
        self.update_lowest_tail_index()


    def pop_data(self, channel_id, num_samples_to_pop):
        """Remove data from the buffer for a given channel."""
        if channel_id < 0 or channel_id >= len(self.channels):
            raise ValueError("Invalid channel ID.")
        channel = self.channels[channel_id]
        tail_index = channel['tail_index']
        head_sample_number = channel['head_sample_number']
        tail_sample_number = channel['tail_sample_number']

        if num_samples_to_pop <= 0 or num_samples_to_pop > (tail_sample_number - head_sample_number):
            raise ValueError("Invalid number of samples to pop.")

        # Calculate the new tail index
        new_tail_index = (tail_index - num_samples_to_pop) % self.buffer_size
        popped_data = channel['data'][new_tail_index:tail_index]
        
        # Update head sample number and tail index
        channel['head_sample_number'] += num_samples_to_pop
        channel['tail_index'] = new_tail_index

        return popped_data # single channel data
    
    def pop_data_all_channels(self, num_samples_to_pop):
        """Remove data from all channels."""
        if num_samples_to_pop <= 0:
            raise ValueError("Number of samples to pop must be positive.")
        
        popped_data = []
        for channel in self.channels:
            if channel['tail_sample_number'] - channel['head_sample_number'] < num_samples_to_pop:
                raise ValueError(f"Not enough data in channel {channel['id']} to pop {num_samples_to_pop} samples.")
            popped_data.append(self.pop_data(channel['id'], num_samples_to_pop))
        
        # Update the lowest tail index after popping data
        self.update_lowest_tail_index()

        return popped_data # list of popped data for each channel
    
    def update_lowest_tail_index(self):
        """Update the lowest tail index across all channels."""
        if not self.channels:
            return
        self.lowest_tail_index = min(channel['tail_index'] for channel in self.channels)



class ZMQClient:

    class ConnectionStatusType(Enum):
        NOT_CONNECTED = 0
        DISCONNECTED = 1
        RECONNECTING = 2
        CONNECTING = 3
        CONNECTED = 4 
        ONLINE = 5
        NOT_RESPONDING = 6


    def __init__(self, ip="localhost", data_port=5556):
        self.context = zmq.Context()
        self.heartbeat_socket = None
        self.data_socket = None
        self.poller = zmq.Poller()
        self.ip = ip
        self.data_port = data_port
        self.message_num = 0
        self.socket_waits_reply = False
        self.uuid = "1618" #str(uuid.uuid4())
        self.app_name = 'Main App ' + self.uuid[:4]
        self.last_heartbeat_timestamp = 0
        self.last_reply_timestamp = time.time()

        # Set the protocol for ZMQ connections
        self.protocol = "tcp://"

        # Calculate heartbeat port based on data port
        self.heartbeat_port = data_port + 1

        # Set Default Heartbeat Timeout
        self.heartbeat_timeout_duration = 2.0  # seconds
        self.not_responding_timeout_duration = 10.0  # seconds

        # Initialize the heartbeat status
        self.connection_status = ZMQClient.ConnectionStatusType.NOT_CONNECTED

        # Initialize the data manager
        self.data_manager = DataManager()
        self.data_manager.init_empty_buffer(num_channels=32, num_samples=60000)

        self.init_socket()

    def init_socket(self):
        self.connection_status = ZMQClient.ConnectionStatusType.CONNECTING

        data_port_address = f'{self.protocol}{self.ip}:{self.data_port}'
        print(f"Connecting to data socket at {data_port_address}")
        self.data_socket = self.context.socket(zmq.SUB)
        self.data_socket.connect(data_port_address)
        self.data_socket.setsockopt(zmq.SUBSCRIBE, b'')
        self.poller.register(self.data_socket, zmq.POLLIN)

        heartbeat_port_address = f'{self.protocol}{self.ip}:{self.heartbeat_port}'
        print(f"Connecting to heartbeat socket at { heartbeat_port_address}")
        self.heartbeat_socket = self.context.socket(zmq.REQ)
        self.heartbeat_socket.connect( heartbeat_port_address)
        self.poller.register(self.heartbeat_socket, zmq.POLLIN)

        self.connection_status = ZMQClient.ConnectionStatusType.CONNECTED

    def send_heartbeat(self):
        d = {'application': self.app_name,
             'uuid': self.uuid,
             'type': 'heartbeat'}
        json_msg = json.dumps(d)
        #print("Sending heartbeat...")
        self.heartbeat_socket.send(json_msg.encode('utf-8'))
        self.last_heartbeat_timestamp = time.time()
        self.socket_waits_reply = True

    def run(self):
        print("Starting ZMQ client loop...")
        while True:
            #print(f"Current connection status: {self.connection_status.name}")
            if (time.time() - self.last_heartbeat_timestamp) > self.heartbeat_timeout_duration:
                if self.socket_waits_reply:
                    self.connection_status = ZMQClient.ConnectionStatusType.NOT_RESPONDING
                    print("Heartbeat hasn't got reply, retrying...")
                    self.last_heartbeat_timestamp += 1.
                    if (time.time() - self.last_reply_timestamp) > self.not_responding_timeout_duration:
                        self.connection_status = ZMQClient.ConnectionStatusType.RECONNECTING
                        print("Connection lost, trying to reconnect...")
                        self.poller.unregister(self.data_socket)
                        self.data_socket.close()
                        self.data_socket = None
                        self.init_socket()
                        self.socket_waits_reply = False
                        self.last_reply_timestamp = time.time()
                else:
                    self.send_heartbeat()

            socks = dict(self.poller.poll(1))
            if not socks:
                continue

            if self.data_socket in socks:
                try:
                    message = self.data_socket.recv_multipart(zmq.NOBLOCK)
                except zmq.ZMQError as err:
                    print(f"ZMQ error: {err}")
                    break
                if message:
                    self.message_num += 1
                    if len(message) < 2:
                        print("No frames for message:", message[0])
                        continue
                    try:
                        #print(f"Received message[0]: {message[0]}")
                        #print(f"Received message[1]: {message[1]}")
                        header = json.loads(message[1].decode('utf-8'))
                    except ValueError as e:
                        print("ValueError:", e)
                        print(message[1])
                        continue
                    if header['message_num'] != self.message_num:
                        print("Missed a message at number", self.message_num)
                    self.message_num = header['message_num']
                    if header['type'] == 'data':
                        c = header['content']
                        # stream_name = c['stream']
                        channel_num = c['channel_num']
                        channel_name = c.get('channel_name', None)
                        num_samples = c['num_samples'] # number of samples per channel
                        # sample_num = c.get('sample_num', None) # sample number in the entire stream
                        # time_stamp = c.get('timestamp', None) # timestamp of the data
                        # sample_rate = c.get('sample_rate', None)

                        print(f"num_samples: {num_samples}, channel_num: {channel_num} {channel_name}")
                        try:
                            n_arr = np.frombuffer(message[2], dtype=np.float32)
                            self.data_manager.push_data(channel_num, n_arr.reshape(-1, num_samples))

                        except IndexError as e:
                            print(e)
                            print(header)
                            print(message[1])
                            if len(message) > 2:
                                print(len(message[2]))
                            else:
                                print("Only one frame???")
                        
                        # print all tail index in the data manager
                        #for channel in self.data_manager.channels:
                        #    print(f"Channel {channel['id']} tail index: {channel['tail_index']}, tail sample number: {channel['tail_sample_number']}")

                        if self.data_manager.lowest_tail_index > 0:
                            print("Lowest tail index:", self.data_manager.lowest_tail_index)
                            datalist = self.data_manager.pop_data_all_channels(self.data_manager.lowest_tail_index)
                            # send all channel data to OSC
                            #for i, data in enumerate(datalist):
                            #    print(f"Sending data for channel {i} to OSC")
                            #    send_data_to_osc(data, address=f"/ch{i:03d}")
                            
                            send_datalist_to_osc(datalist)


                    elif header['type'] == 'event':
                        if header['data_size'] > 0:
                            event = OpenEphysEventObject(header['content'], message[2])
                        else:
                            event = OpenEphysEventObject(header['content'])
                        print("Event received:", event)
                    elif header['type'] == 'spike':
                        spike = OpenEphysSpikeObject(header['spike'], message[2])
                        print("Spike received:", spike)
                    else:
                        print("Unknown message type:", header['type'])
                else:
                    print("No data in message, breaking")

            elif self.heartbeat_socket in socks and self.socket_waits_reply:
                message = self.heartbeat_socket.recv()
                #print(f'Heartbeat reply: {message}')
                self.connection_status = ZMQClient.ConnectionStatusType.ONLINE
                if self.socket_waits_reply:
                    self.socket_waits_reply = False
                else:
                    print("Received reply before sending a message?")


def send_datalist_to_osc(datalist, address="/data"):
    """
    Function to send a list of data to an OSC server.
    This is a placeholder function and should be implemented based on your OSC library.
    """
    # convert datalist to 2D numpy array if it's not already
    if isinstance(datalist, list):
        datalist = np.array(datalist)
    if not isinstance(datalist, np.ndarray):
        raise ValueError("datalist must be a list or numpy array.")
    
    # transpose
    datalist = datalist.T  # Transpose to have channels as rows
    
    client = udp_client.SimpleUDPClient("127.0.0.1", 10000)  # Replace with your OSC server address and port
   
    # loop each sample
    for i, data in enumerate(datalist):
        client.send_message(address, data.tolist())
                                        

def send_data_to_osc(data, address="/data"):
    """
    Function to send data to an OSC server.
    This is a placeholder function and should be implemented based on your OSC library.
    """

    #convert data from np.ndarray to list if needed
    if isinstance(data, np.ndarray):
        data = data.tolist()

    client = udp_client.SimpleUDPClient("127.0.0.1", 10000)  # Replace with your OSC server address and port
    if isinstance(data, list):
        for item in data:
            client.send_message(address, item)
    else:
        client.send_message(address, data) 



if __name__ == "__main__":
    client = ZMQClient()
    client.run()
