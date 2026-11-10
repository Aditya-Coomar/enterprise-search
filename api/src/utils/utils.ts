const generateUniqueID = () => {
  const now = new Date();

  // Format date as YYYYMMDD
  const datePart = now.toISOString().slice(0, 10).replace(/-/g, '');

  // Format time as HHMMSSmmm (milliseconds)
  const timePart =
    now
      .toTimeString()
      .slice(0, 8) // HH:MM:SS
      .replace(/:/g, '') + now.getMilliseconds().toString().padStart(3, '0');

  // Add microseconds using performance.now()
  const microPart = Math.floor((performance.now() % 1) * 1000000)
    .toString()
    .padStart(6, '0');

  return `${datePart}${timePart}${microPart}`;
};

const getISTDateTimeRange = (dateReference: string) => {
  // Get current UTC time
  const now = new Date();

  // Convert to IST by using toLocaleString with 'en-US' and 'Asia/Kolkata' timeZone
  const getISTDate = (date: Date) => {
    const istString = date.toLocaleString('en-US', {
      timeZone: 'Asia/Kolkata',
    });
    return new Date(istString);
  };

  const format = (date: Date) =>
    date.toISOString().replace('T', ' ').slice(0, 16);

  // Handle specific keywords
  if (dateReference === 'today') {
    const targetDate = getISTDate(now);
    const startDate = new Date(targetDate);
    startDate.setHours(0, 0, 0, 0);
    const endDate = new Date(targetDate);
    endDate.setHours(23, 59, 0, 0);

    return {
      start: format(startDate),
      end: format(endDate),
    };
  }

  if (dateReference === 'yesterday') {
    const targetDate = getISTDate(now);
    targetDate.setDate(targetDate.getDate() - 1);
    const startDate = new Date(targetDate);
    startDate.setHours(0, 0, 0, 0);
    const endDate = new Date(targetDate);
    endDate.setHours(23, 59, 0, 0);

    return {
      start: format(startDate),
      end: format(endDate),
    };
  }

  // Handle date ranges like "last 3 days", "past week", etc.
  const rangePattern =
    /(?:last|past)\s+(\d+)\s+(day|days|week|weeks|month|months)/i;
  const rangeMatch = dateReference.match(rangePattern);

  if (rangeMatch) {
    const count = parseInt(rangeMatch[1]);
    const unit = rangeMatch[2].toLowerCase();
    const endDate = getISTDate(now);
    endDate.setHours(23, 59, 0, 0);

    const startDate = new Date(endDate);

    if (unit.startsWith('day')) {
      startDate.setDate(startDate.getDate() - count + 1);
    } else if (unit.startsWith('week')) {
      startDate.setDate(startDate.getDate() - count * 7 + 1);
    } else if (unit.startsWith('month')) {
      startDate.setMonth(startDate.getMonth() - count);
    }

    startDate.setHours(0, 0, 0, 0);

    return {
      start: format(startDate),
      end: format(endDate),
    };
  }

  // Handle specific date formats (YYYY-MM-DD)
  const datePattern = /^\d{4}-\d{2}-\d{2}$/;
  if (datePattern.test(dateReference)) {
    try {
      const targetDate = new Date(dateReference + 'T00:00:00');
      const startDate = new Date(targetDate);
      startDate.setHours(0, 0, 0, 0);
      const endDate = new Date(targetDate);
      endDate.setHours(23, 59, 0, 0);

      return {
        start: format(startDate),
        end: format(endDate),
      };
    } catch (error) {
      return null;
    }
  }

  // Handle date with day and month (e.g., "20th Sep", "15th September", "3rd Jan")
  const dayMonthPattern =
    /(\d{1,2})(?:st|nd|rd|th)?\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|september|oct|october|nov|november|dec|december)/i;
  const dayMonthMatch = dateReference.match(dayMonthPattern);

  if (dayMonthMatch) {
    try {
      const day = parseInt(dayMonthMatch[1]);
      const monthStr = dayMonthMatch[2].toLowerCase();

      // Map month names to numbers
      const monthMap: { [key: string]: number } = {
        jan: 0,
        january: 0,
        feb: 1,
        february: 1,
        mar: 2,
        march: 2,
        apr: 3,
        april: 3,
        may: 4,
        jun: 5,
        june: 5,
        jul: 6,
        july: 6,
        aug: 7,
        august: 7,
        sep: 8,
        september: 8,
        oct: 9,
        october: 9,
        nov: 10,
        november: 10,
        dec: 11,
        december: 11,
      };

      const month = monthMap[monthStr];
      if (month === undefined) return null;

      // Use current year
      const currentYear = getISTDate(now).getFullYear();
      const targetDate = new Date(currentYear, month, day);

      const startDate = new Date(targetDate);
      startDate.setHours(0, 0, 0, 0);
      const endDate = new Date(targetDate);
      endDate.setHours(23, 59, 0, 0);

      return {
        start: format(startDate),
        end: format(endDate),
      };
    } catch (error) {
      return null;
    }
  }

  // Handle day only (e.g., "20th", "15th", "3rd")
  const dayOnlyPattern = /^(\d{1,2})(?:st|nd|rd|th)?$/;
  const dayOnlyMatch = dateReference.match(dayOnlyPattern);

  if (dayOnlyMatch) {
    try {
      const day = parseInt(dayOnlyMatch[1]);

      // Use current year and month
      const currentDate = getISTDate(now);
      const currentYear = currentDate.getFullYear();
      const currentMonth = currentDate.getMonth();

      const targetDate = new Date(currentYear, currentMonth, day);

      const startDate = new Date(targetDate);
      startDate.setHours(0, 0, 0, 0);
      const endDate = new Date(targetDate);
      endDate.setHours(23, 59, 0, 0);

      return {
        start: format(startDate),
        end: format(endDate),
      };
    } catch (error) {
      return null;
    }
  }

  // Handle date ranges (YYYY-MM-DD to YYYY-MM-DD)
  const dateRangePattern =
    /(\d{4}-\d{2}-\d{2})\s*(?:to|until|-)\s*(\d{4}-\d{2}-\d{2})/i;
  const dateRangeMatch = dateReference.match(dateRangePattern);

  if (dateRangeMatch) {
    try {
      const startDate = new Date(dateRangeMatch[1] + 'T00:00:00');
      const endDate = new Date(dateRangeMatch[2] + 'T23:59:00');

      return {
        start: format(startDate),
        end: format(endDate),
      };
    } catch (error) {
      return null;
    }
  }

  // If no pattern matches, return null
  return null;
};

// Helper function to parse multiple date references
const parseMultipleDateReferences = (
  dateReferences: string[],
): Array<{ start: string; end: string }> => {
  const dateRanges: Array<{ start: string; end: string }> = [];

  for (const dateRef of dateReferences) {
    const range = getISTDateTimeRange(dateRef);
    if (range) {
      dateRanges.push(range);
    }
  }

  return dateRanges;
};

// Helper function to optimize date ranges by merging overlapping ones
const optimizeDateRanges = (
  ranges: Array<{ start: string; end: string }>,
): Array<{ start: string; end: string }> => {
  if (ranges.length <= 1) return ranges;

  // Sort ranges by start date
  ranges.sort(
    (a, b) => new Date(a.start).getTime() - new Date(b.start).getTime(),
  );

  const merged: Array<{ start: string; end: string }> = [ranges[0]];

  for (let i = 1; i < ranges.length; i++) {
    const current = ranges[i];
    const last = merged[merged.length - 1];

    // Check if current range overlaps with the last merged range
    if (new Date(current.start).getTime() <= new Date(last.end).getTime()) {
      // Merge ranges
      last.end = new Date(
        Math.max(new Date(current.end).getTime(), new Date(last.end).getTime()),
      )
        .toISOString()
        .replace('T', ' ')
        .slice(0, 16);
    } else {
      // Add non-overlapping range
      merged.push(current);
    }
  }

  return merged;
};

export {
  generateUniqueID,
  getISTDateTimeRange,
  parseMultipleDateReferences,
  optimizeDateRanges,
};
