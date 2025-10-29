import rtmidi, array, time

midi_out = rtmidi.MidiOut()
ports = [midi_out.getPortName(i) for i in range(midi_out.getPortCount())]
print("Ports:", ports)
midi_out.openPort(0)  # выберите нужный индекс

note_on = array.array('B', [0x90, 60, 100])  # Note On (C4)
note_off = array.array('B', [0x80, 60, 0])   # Note Off

midi_out.sendMessage(note_on)
time.sleep(1)
midi_out.sendMessage(note_off)
