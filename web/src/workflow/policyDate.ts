const BUSINESS_TIME_ZONE = "Asia/Seoul";

export function policyAsOfDate(receivedAt: string): string {
  const value = new Date(receivedAt);
  if (Number.isNaN(value.getTime())) {
    throw new Error("정책 기준일을 확인할 수 없습니다. 접수 시각을 다시 확인해 주세요.");
  }
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: BUSINESS_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const read = (type: Intl.DateTimeFormatPartTypes): string | undefined =>
    parts.find((part) => part.type === type)?.value;
  const year = read("year");
  const month = read("month");
  const day = read("day");
  if (!year || !month || !day) {
    throw new Error("정책 기준일을 확인할 수 없습니다. 접수 시각을 다시 확인해 주세요.");
  }
  return `${year}-${month}-${day}`;
}
