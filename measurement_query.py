"""Small, explicit queries over saved measurements and current device notes."""

from dataclasses import dataclass
from datetime import date
import operator

from sample_map_model import date_text


FIELDS = ('Procedure', 'Site', 'Subsite', 'Device', 'Date', 'Device status', 'Notes',
          'Has notes', 'Has plot', 'Metadata warning', 'Filename')
COMPARISONS = {'>': operator.gt, '>=': operator.ge, '<': operator.lt, '<=': operator.le,
               'after': operator.gt, 'on or after': operator.ge,
               'before': operator.lt, 'on or before': operator.le}


def field_value(item, field, annotation):
    if field in ('Chip', 'Site', 'Subsite', 'Device'):
        return getattr(item.identity, field.lower())
    if field == 'Date':
        return date_text(item.timestamp)
    if field == 'Device status':
        return annotation.get('status') or 'Untagged'
    if field == 'Notes':
        return annotation.get('notes', '')
    if field == 'Has notes':
        return 'Yes' if annotation.get('has_notes') else 'No'
    if field == 'Has plot':
        return 'Yes' if item.plot_files else 'No'
    if field == 'Metadata warning':
        return 'Yes' if item.warnings else 'No'
    if field == 'Filename':
        return item.name
    return item.metadata.get(field, '')


@dataclass(frozen=True)
class Condition:
    field: str
    comparison: str
    value: str

    def validate(self):
        if self.comparison not in ('contains', 'is', 'is not', *COMPARISONS):
            raise ValueError('Choose a comparison.')
        if self.field == 'Date':
            try:
                if date.fromisoformat(self.value).isoformat() != self.value:
                    raise ValueError()
            except ValueError:
                raise ValueError('Enter dates as YYYY-MM-DD.') from None
        elif self.comparison in COMPARISONS:
            try:
                float(self.value)
            except ValueError:
                raise ValueError(f'Enter a number for {self.field}.') from None

    def matches(self, item, annotation):
        actual = str(field_value(item, self.field, annotation))
        if self.comparison in COMPARISONS:
            if not actual:
                return False
            if self.field == 'Date':
                return COMPARISONS[self.comparison](actual, self.value)
            try:
                return COMPARISONS[self.comparison](float(actual), float(self.value))
            except ValueError:
                return False
        if self.comparison == 'contains':
            return self.value.casefold() in actual.casefold()
        # Missing metadata does not match an exclusion condition either.
        if not actual:
            return False
        equal = actual.casefold() == self.value.casefold()
        if self.field not in FIELDS and self.field != 'Chip':
            try:
                equal = float(actual) == float(self.value)
            except ValueError:
                pass
        return not equal if self.comparison == 'is not' else equal


@dataclass(frozen=True)
class MeasurementQuery:
    text: str = ''
    conditions: tuple = ()
    match_any: bool = False
    from_date: str = ''
    to_date: str = ''

    @property
    def active(self):
        return bool(self.text or self.conditions or self.from_date or self.to_date)

    def validate(self):
        for value in (self.from_date, self.to_date):
            if value:
                Condition('Date', 'is', value).validate()
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError('From must be on or before To.')
        for condition in self.conditions:
            condition.validate()

    def matches(self, item, annotation):
        if self.from_date or self.to_date:
            day = date_text(item.timestamp)
            if (not day or (self.from_date and day < self.from_date)
                    or (self.to_date and day > self.to_date)):
                return False
        text = ' '.join((item.name, item.timestamp, item.identity.label,
                         *map(str, item.metadata.values()), annotation.get('notes', ''),
                         annotation.get('status', ''))).casefold()
        if not all(word in text for word in self.text.casefold().split()):
            return False
        if not self.conditions:
            return True
        results = (condition.matches(item, annotation) for condition in self.conditions)
        return any(results) if self.match_any else all(results)


def find_devices(identities, text):
    term = text.strip().casefold()
    if not term:
        return set()
    exact = {identity for identity in identities if term in [part.casefold() for part in identity.parts[1:]]}
    return exact or {identity for identity in identities
                     if all(word in '/'.join(identity.parts[1:]).casefold() for word in term.split())}
