"""Wire fixtures independently matched to scrcpy v4.1 ControlMessageReader."""
import unittest

from scrcpy_probe import key_packet, touch_packet


class ProtocolTest(unittest.TestCase):
    def test_key_enter_up(self):
        self.assertEqual(key_packet(1, 66), bytes.fromhex('00 01 00000042 00000000 00000000'))

    def test_finger_down(self):
        self.assertEqual(touch_packet(0, 100, 200, 1080, 1920), bytes.fromhex(
            '02 00 fffffffffffffffe 00000064 000000c8 0438 0780 ffff 00000000 00000000'))

    def test_prohibited_key(self):
        for keycode in (3, 26, 224):
            with self.assertRaises(ValueError):
                key_packet(0, keycode)

    def test_invalid_coordinates(self):
        for x, y in ((-1, 1), (720, 1), (1, -1), (1, 1280)):
            with self.assertRaises(ValueError):
                touch_packet(0, x, y, 720, 1280)


if __name__ == '__main__':
    unittest.main()
