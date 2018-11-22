

class Packet:
    def __init__(self, seq, ack, syn=0, fin=0, data=''):
        self.seq_num=seq
        self.ack_num=ack
        self.syn=syn
        self.fin=fin
        self.data=data


def write_in_logfile(send_or_receive, transmit_time, type, packet, filename):
    print('{:<5} {:<9} {:<3} {:<5} {:<5} {}'.format(send_or_receive, round(transmit_time * 1000, 2), type,
                                     packet.seq_num, len(packet.data), packet.ack_num))
    print('{:<5} {:<9} {:<3} {:<5} {:<5} {}'.format(send_or_receive, round(transmit_time * 1000, 2), type,
                                     packet.seq_num, len(packet.data), packet.ack_num), file=filename)