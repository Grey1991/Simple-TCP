from sys import *
import socket
import time
import pickle
import threading
from random import *
# from packet import *
import argparse

mytime = None
if platform == 'win32':
    mytime = time.clock
else:
    mytime = time.time
assert(mytime is not None)

class Packet:
    def __init__(self, seq, ack, syn=0, fin=0, data=''):
        self.seq_num = seq
        self.ack_num = ack
        self.syn = syn
        self.fin = fin
        self.data = data


def write_in_logfile(send_or_receive, transmit_time, type, packet, filename):
    print('{:<5} {:<9} {:<3} {:<5} {:<5} {}'.format(send_or_receive, round(transmit_time * 1000, 2), type,
                                     packet.seq_num, len(packet.data), packet.ack_num))
    print('{:<5} {:<9} {:<3} {:<5} {:<5} {}'.format(send_or_receive, round(transmit_time * 1000, 2), type,
                                     packet.seq_num, len(packet.data), packet.ack_num), file=filename)

class STP_sender(object):

    def __init__(self, receiver_host_ip, receiver_port, filename, MWS, MSS, my_timeout, pdrop, my_seed):
        self.params_check(MWS, MSS)
        self.destination = (receiver_host_ip, receiver_port)
        self.filename = filename
        self.MWS = MWS
        self.MSS = MSS
        self.pdrop = pdrop
        self.seed = my_seed

        self.filelength = 0
        self.segments_dic = {}
        self.my_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.start_time = mytime()
        self.INIT_TIMEOUT = my_timeout
        self.my_timeout = my_timeout
        self.my_socket.settimeout(my_timeout)
        self.client_isn = 121
        self.rcv_buff = 1024
        self.sender_ack = 0
        self.sender_log = open('Sender_log.txt', 'w')
        self.timer_start_time = 0
        self.sender_base = self.client_isn + 1
        self.current_send = self.sender_base
        self.window_end = self.sender_base + self.MWS - self.MSS
        self.duplicate_ack = 0
        self.lock1 = threading.Lock()
        self.lock2 = threading.Lock()

        self.shutdown_flag = self.timeout_flag = self.window_move_flag = self.sender_flag = False

    def params_check(self, MSW, MSS):
        if int(MSW) < int(MSS):
            print('Sorry, incorrect input.')
            exit()

    def three_way_handshake(self):
        syn_packet1 = Packet(self.client_isn, 0, syn=1)
        self.my_socket.sendto(pickle.dumps(syn_packet1), self.destination)
        write_in_logfile('snd', mytime()-self.start_time, 'S', syn_packet1, self.sender_log)
        data, addr = self.my_socket.recvfrom(self.rcv_buff)
        receive_message = pickle.loads(data)
        write_in_logfile('rcv', mytime()-self.start_time, 'SA', receive_message, self.sender_log)
        if receive_message.syn == 1 and receive_message.ack_num == syn_packet1.seq_num + 1:
            self.sender_ack = receive_message.seq_num + 1
            syn_packet2 = Packet(receive_message.ack_num, receive_message.seq_num +1)
            self.my_socket.sendto(pickle.dumps(syn_packet2), self.destination)
            write_in_logfile('snd', mytime()-self.start_time, 'A', syn_packet2, self.sender_log)
            print('Connection established')
            self.transmission()

    def shutdown(self):
        fin_packet1 = Packet(self.client_isn + self.filelength + 1, self.sender_ack, fin=1)
        self.my_socket.sendto(pickle.dumps(fin_packet1), self.destination)
        write_in_logfile('snd', mytime()-self.start_time, 'F', fin_packet1, self.sender_log)
        while True:
            data, addr = self.my_socket.recvfrom(self.rcv_buff)
            receive_message = pickle.loads(data)
            if receive_message.fin == 1 and receive_message.ack_num == fin_packet1.seq_num + 1:
                write_in_logfile('rcv', mytime()-self.start_time, 'FA', receive_message, self.sender_log)
                fin_packet2 = Packet(receive_message.ack_num, self.sender_ack + 1)
                self.my_socket.sendto(pickle.dumps(fin_packet2), self.destination)
                write_in_logfile('snd', mytime()-self.start_time, 'A', fin_packet2, self.sender_log)
                break
        self.my_socket.close()
        self.sender_log.close()
        print('sender shutdown')

    def generate_segments(self):
        with open(self.filename) as fobj:
            content = fobj.read()
            self.filelength = len(content)
            splitdata = [content[i:i+self.MSS] for i in range(0, len(content), self.MSS)]
            segments = [Packet(self.client_isn + 1 + self.MSS*i, self.sender_ack, data=splitdata[i])
                        for i in range(0, len(splitdata))]
            # print(segments[0].seq_num,segments[0].data)
            # print(segments[1].seq_num,segments[1].data)
            # print(len(segments))
            self.segments_dic = {self.client_isn + 1 + i*self.MSS: segments[i]
                                 for i in range(0, len(segments))}
            # print(self.segments_dic)

    def PLD_Module(self, packet):
        if random()>self.pdrop:
            self.my_socket.sendto(pickle.dumps(packet), self.destination)
            self.lock2.acquire()
            write_in_logfile('snd',mytime()-self.start_time,'D',packet,self.sender_log)
            self.lock2.release()
        else:
            self.lock2.acquire()
            write_in_logfile('drop',mytime()-self.start_time,'D',packet,self.sender_log)
            self.lock2.release()

    def send_packet(self):
        while self.current_send <= self.window_end:
            if self.timeout_flag:
                self.PLD_Module(self.segments_dic[self.sender_base])
                self.timeout_flag = False
            elif self.current_send == self.client_isn+1+self.filelength:
                break
            else:
                self.PLD_Module(self.segments_dic[self.current_send])
                self.current_send += len(self.segments_dic[self.current_send].data)

    def cumulative_acknowledgement_and_move_window(self,received_message):
        self.timer_start_time = mytime()
        self.window_end += received_message.ack_num - self.sender_base
        self.sender_base = received_message.ack_num
        self.window_move_flag = True

    def receive_ack(self):
            try:
                data, addr = self.my_socket.recvfrom(self.rcv_buff)
                # print('received')
                received_message = pickle.loads(data)
                self.lock2.acquire()
                write_in_logfile('rcv',mytime()-self.start_time,'A',received_message,self.sender_log)
                self.lock2.release()
                if received_message.ack_num == self.client_isn + 1 + self.filelength:
                    self.shutdown_flag = True
                if received_message.ack_num > self.sender_base:
                    self.cumulative_acknowledgement_and_move_window(received_message)
                elif received_message.ack_num == self.sender_base:
                    self.duplicate_ack += 1
            except socket.timeout:
                self.timeout_flag = True
                self.timer_start_time = mytime()

    def send_thread(self):
        self.sender_flag = True
        seed(self.seed)
        self.generate_segments()
        self.timer_start_time = mytime()
        if len(self.segments_dic) == 0:
            self.shutdown_flag = True
            return
        while True:
            if self.timeout_flag:
                self.lock1.acquire()
                self.PLD_Module(self.segments_dic[self.sender_base])
                self.timeout_flag = False
                self.lock1.release()
                continue
            elif self.shutdown_flag:
                # print('shutdown flag')
                break
            else:
                self.send_packet()
            self.window_move_flag = False
            while True:
                if self.window_move_flag or self.timeout_flag or self.shutdown_flag:
                    break
        self.sender_flag = False
        # print(self.sender_flag)
        # print('shutdown flag')

    def receive_thread(self):
        while True:
            if self.shutdown_flag:
                break
            if mytime() - self.timer_start_time > self.my_timeout:
                self.timeout_flag = True
                self.timer_start_time = mytime()
                continue
            if self.duplicate_ack == 3:
                self.timeout_flag = True
                self.timer_start_time = mytime()
                self.duplicate_ack = 0
                continue
            if self.sender_flag:
                self.receive_ack()
                continue
            else:
                break
        # print('receive shutdown')

    def transmission(self):
        thread1 = threading.Thread(target=self.send_thread)
        thread2 = threading.Thread(target=self.receive_thread)
        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()
        print('transmission finished')
        self.shutdown()



if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("port")
    parser.add_argument("filename")
    parser.add_argument("MWS")
    parser.add_argument("MSS")
    parser.add_argument("my_timeout")
    parser.add_argument("pdrop")
    parser.add_argument("my_seed")
    args = parser.parse_args()

    host = args.host
    port = int(args.port)
    MSS = int(args.MSS)
    pdrop = float(args.pdrop)
    my_timeout = float(args.my_timeout)/1000
    filename = args.filename
    MWS = int(args.MWS)
    my_seed = int(args.my_seed)

    # host = '127.0.0.1'
    # port = 3000
    # filename = 'test1.txt'
    # MWS = 800
    # MSS = 200
    # my_timeout = 0.04
    # pdrop = 0.4
    # my_seed = 100
    #
    # host = '127.0.0.1'
    # port = 3000
    # filename = 'test4.txt'
    # MWS = 600
    # MSS = 50
    # my_timeout = 0.007
    # pdrop = 0.3
    # my_seed = 10

    stp_sender = STP_sender(host, port, filename, MWS, MSS, my_timeout, pdrop, my_seed)
    stp_sender.three_way_handshake()

    log_content = []
    seq_list = []
    ack_list = []
    drop_list = []
    with open('Sender_log.txt') as file:
        for line in file:
            log_content.append(line.split())
    for i in log_content:
        if i[0] == 'snd' and i[2] == 'D':
            seq_list.append(i[3])
        if i[0] == 'rcv' and i[2] == 'A':
            ack_list.append(i[5])
        if i[0] == 'drop':
            drop_list.append(i[3])
    data_num = stp_sender.filelength
    seg_num = len(set(seq_list))
    drop_num = len(drop_list)
    retrans_num = len(seq_list) - seg_num + len(drop_list)
    duplicate_ack_num = len(ack_list) - len(set(ack_list))
    log = open('Sender_log.txt','a')
    log.write('\n'
              'Amount of (original) Data Transferred: '+str(data_num)+'\n'
              'Number of Data Segments Sent: '+str(seg_num)+'\n'
              'Number of (all) Packets Dropped: '+str(drop_num)+'\n'
              'Number of Retransmitted Segments: '+str(retrans_num)+'\n'
              'Number of Duplicate Acknowledgements received: '+str(duplicate_ack_num)+'\n')
    log.close()
    print('\n'
          'Amount of (original) Data Transferred: ' + str(data_num) + '\n'
          'Number of Data Segments Sent: '+str(seg_num)+'\n'
          'Number of (all) Packets Dropped: '+str(drop_num)+'\n'
          'Number of Retransmitted Segments: ' + str(retrans_num) + '\n'
          'Number of Duplicate Acknowledgements received: ' + str(duplicate_ack_num) + '\n')

    # time_test = open('Time_test_1.txt','a')
    # time_test.write('{:<3} {:<3}\n'.format(my_timeout*1000, retrans_num))





