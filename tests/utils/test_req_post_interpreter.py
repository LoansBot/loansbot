"""Very sophisticated test which just imports everything.
"""
import unittest
import helper  # noqa
from utils.req_post_interpreter import (LoanRequest, interpret)


class Test(unittest.TestCase):
    def test_interpret_empty(self):
        result = interpret('')
        self.assertIsInstance(result, LoanRequest)
        self.assertEqual(result.title, '')
        self.assertIsNone(result.location)
        self.assertIsNone(result.city)
        self.assertIsNone(result.state)
        self.assertIsNone(result.country)
        self.assertIsNone(result.terms)
        self.assertIsNone(result.processor)
        self.assertEqual(result.notes, [])

    def test_interpret_no_blobs(self):
        result = interpret('[REQ] Stuff')
        self.assertIsInstance(result, LoanRequest)
        self.assertEqual(result.title, '[REQ] Stuff')
        self.assertIsNone(result.location)
        self.assertIsNone(result.city)
        self.assertIsNone(result.state)
        self.assertIsNone(result.country)
        self.assertIsNone(result.terms)
        self.assertIsNone(result.processor)
        self.assertEqual(result.notes, [])

    def test_interpret_one_note(self):
        result = interpret('[REQ] (foobar)')
        self.assertIsInstance(result, LoanRequest)
        self.assertEqual(result.title, '[REQ] (foobar)')
        self.assertIsNone(result.location)
        self.assertIsNone(result.city)
        self.assertIsNone(result.state)
        self.assertIsNone(result.country)
        self.assertIsNone(result.terms)
        self.assertIsNone(result.processor)
        self.assertEqual(result.notes, ['foobar'])

    def test_interpret_location(self):
        result = interpret('[REQ] (#City, State, Country)')
        self.assertIsInstance(result, LoanRequest)
        self.assertEqual(result.title, '[REQ] (#City, State, Country)')
        self.assertEqual(result.location, 'City, State, Country')
        self.assertEqual(result.city, 'City')
        self.assertEqual(result.state, 'State')
        self.assertEqual(result.country, 'Country')
        self.assertIsNone(result.terms)
        self.assertIsNone(result.processor)
        self.assertEqual(result.notes, [])

    def test_interpret_terms(self):
        result = interpret('[REQ] ($325 by 31/8/20)')
        self.assertIsInstance(result, LoanRequest)
        self.assertIsNone(result.location)
        self.assertIsNone(result.city)
        self.assertIsNone(result.state)
        self.assertIsNone(result.country)
        self.assertEqual(result.terms, '$325 by 31/8/20')
        self.assertIsNone(result.processor)
        self.assertEqual(result.notes, [])

    def test_interpret_processor(self):
        processors = ['venmo', 'paypal', 'bank', 'cashapp', 'zelle', 'chime']
        for processor in processors:
            title = f'[REQ] ({processor})'
            result = interpret(title)
            self.assertIsInstance(result, LoanRequest)
            self.assertIsNone(result.location)
            self.assertIsNone(result.city)
            self.assertIsNone(result.state)
            self.assertIsNone(result.country)
            self.assertIsNone(result.terms)
            self.assertEqual(result.processor, processor)
            self.assertEqual(result.notes, [])

    def test_interpret_sample_a(self):
        title = '[Req] (#Frederick, MD, USA) (8/22/2020) (Cashapp Chime)'
        result = interpret(title)
        self.assertIsInstance(result, LoanRequest)
        self.assertEqual(result.title, title)
        self.assertEqual(result.location, 'Frederick, MD, USA')
        self.assertEqual(result.city, 'Frederick')
        self.assertEqual(result.state, 'MD')
        self.assertEqual(result.country, 'USA')
        self.assertEqual(result.terms, '8/22/2020')
        self.assertEqual(result.processor, 'Cashapp Chime')
        self.assertEqual(result.notes, [])

    def test_interpret_sample_b(self):
        title = '[Req] ($800) - (#Clinton, Indiana, USA) (Would like to repay in 4 transactions if possible)'
        result = interpret(title)
        self.assertIsInstance(result, LoanRequest)
        self.assertEqual(result.title, title)
        self.assertEqual(result.location, 'Clinton, Indiana, USA')
        self.assertEqual(result.city, 'Clinton')
        self.assertEqual(result.state, 'Indiana')
        self.assertEqual(result.country, 'USA')
        self.assertEqual(result.terms, '$800')
        self.assertIsNone(result.processor)
        self.assertEqual(result.notes, ['Would like to repay in 4 transactions if possible'])

    def test_interpret_sample_c(self):
        title = '[REQ] ($25) - (#Fort Wayne, Indiana, USA), (repay $35 on 9/28/20) (PayPal, Cashapp, Venmo)'
        result = interpret(title)
        self.assertIsInstance(result, LoanRequest)
        self.assertEqual(result.title, title)
        self.assertEqual(result.location, 'Fort Wayne, Indiana, USA')
        self.assertEqual(result.city, 'Fort Wayne')
        self.assertEqual(result.state, 'Indiana')
        self.assertEqual(result.country, 'USA')
        self.assertEqual(result.terms, '$25')
        self.assertEqual(result.processor, 'PayPal, Cashapp, Venmo')
        self.assertEqual(result.notes, ['repay $35 on 9/28/20'])

    def test_interpret_sample_d(self):
        title = '[REQ] (£200) - (#Nr. Bedford, Bedfordshire, UK), (£240 paid back 28th August 2020) (Paypal).'
        result = interpret(title)
        self.assertIsInstance(result, LoanRequest)
        self.assertEqual(result.title, title)
        self.assertEqual(result.location, 'Nr. Bedford, Bedfordshire, UK')
        self.assertEqual(result.city, 'Nr. Bedford')
        self.assertEqual(result.state, 'Bedfordshire')
        self.assertEqual(result.country, 'UK')
        self.assertEqual(result.terms, '£200')
        self.assertEqual(result.processor, 'Paypal')
        self.assertEqual(result.notes, ['£240 paid back 28th August 2020'])

    def test_interpret_sample_e(self):
        title = '[REQ] ($9 CAD) - (#Brampton, ON, Canada), (10/01/2020) (Pre-Arranged)'
        result = interpret(title)
        self.assertIsInstance(result, LoanRequest)
        self.assertEqual(result.title, title)
        self.assertEqual(result.location, 'Brampton, ON, Canada')
        self.assertEqual(result.city, 'Brampton')
        self.assertEqual(result.state, 'ON')
        self.assertEqual(result.country, 'Canada')
        self.assertEqual(result.terms, '$9 CAD')
        self.assertIsNone(result.processor)
        self.assertEqual(result.notes, ['10/01/2020', 'Pre-Arranged'])


if __name__ == '__main__':
    unittest.main()
