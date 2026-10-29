"""Regressions supplied by the independent v1.0.0 review, recreated locally."""
import copy
import unittest

from memory_interference.generator import digest, make_record
from memory_interference.render import render
from memory_interference.validation import check_record, positional_predictions, strict_equal


def record(**kwargs):
    settings=dict(world=digest('amendment-fixture'),split='test',n_events=48,delay=12,
                  n_revisions=1,mode='current',interference='near_identity',recall=True)
    settings.update(kwargs)
    return make_record(**settings)


class AmendmentRegressions(unittest.TestCase):
    def test_gold_boolean_and_integral_float_revision_rejected(self):
        for value in (True, 1.0):
            r=record(); r['target']['revision']=value
            with self.subTest(value=value),self.assertRaises(AssertionError): check_record(r)

    def test_unset_query_identity_types_rejected_after_prompt_refresh(self):
        for field in ('entity','key'):
            for value in (True,1,1.0):
                r=record(status='unset');r['query'][field]=value
                r['prompt'],r['evidence']=render(r['events'],r['query'],r['target'])
                with self.subTest(field=field,value=value),self.assertRaises(AssertionError):check_record(r)

    def test_nested_span_and_event_numeric_types_rejected(self):
        for container,field in (('event_span',0),('answer_span',1)):
            r=record();r['evidence'][container][field]=float(r['evidence'][container][field])
            with self.subTest(container=container),self.assertRaises(AssertionError):check_record(r)
        for field in ('position','revision'):
            r=record();r['events'][0][field]=float(r['events'][0][field])
            with self.subTest(field=field),self.assertRaises(AssertionError):check_record(r)

    def test_asof_cutoff_gap_is_positive_and_variable(self):
        gaps=set()
        for i in range(30):
            r=record(world=digest('cutoff-regression',i),n_revisions=3,mode='as_of')
            source=next(e for e in r['events'] if e['id']==r['target']['event_id'])
            q=r['query'];at_cutoff=r['events'][q['cutoff']-1]
            self.assertGreater(q['cutoff'],source['position'])
            self.assertNotEqual((at_cutoff['entity'],at_cutoff['key']),(q['entity'],q['key']))
            self.assertNotEqual(at_cutoff['id'],r['target']['event_id'])
            gaps.add(q['cutoff']-source['position'])
            check_record(r)
        self.assertGreaterEqual(len(gaps),3)

    def test_tight_delay_high_revision_asof_still_has_gap(self):
        for i in range(12):
            r=record(world=digest('tight-cutoff-regression',i),delay=8,n_revisions=8,mode='as_of')
            source=next(e for e in r['events'] if e['id']==r['target']['event_id'])
            self.assertGreater(r['query']['cutoff'],source['position'])
            check_record(r)

    def test_review_fixed_rule_fails_asof_even_with_one_revision(self):
        for revisions in (1,3,8):
            r=record(n_revisions=revisions,mode='as_of')
            predictions=positional_predictions(r)
            self.assertTrue(all(not strict_equal(p,r['target']) for p in predictions.values()))

    def test_query_and_factor_numbers_forbid_boolean_and_float(self):
        for field in ('cutoff','revision'):
            for value in (True,1.0):
                r=record(mode='revision');r['query'][field]=value
                with self.subTest(field=field,value=value),self.assertRaises(AssertionError):check_record(r)
        for field in ('event_count','answer_delay','revision_count','cutoff_gap'):
            r=record(mode='as_of');r['factors'][field]=float(r['factors'][field])
            with self.subTest(field=field),self.assertRaises(AssertionError):check_record(r)

    def test_certificate_and_event_primitive_types_are_checked(self):
        r=record();r['certificate']['eligible_mutations']=tuple(r['certificate']['eligible_mutations'])
        with self.assertRaises(AssertionError):check_record(r)
        for field,value in [('entity',True),('key',0),('label',False),('op',True),('ref',False),('value',7)]:
            r=record();r['events'][0][field]=value
            with self.subTest(field=field),self.assertRaises(AssertionError):check_record(r)


if __name__=='__main__':unittest.main()
