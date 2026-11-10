/** Local calendar date as YYYY-MM-DD. Uses the browser's date, not UTC. */
export function todayInput(now = new Date()) {
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${now.getFullYear()}-${month}-${day}`
}

/** Local calendar month as YYYY-MM. */
export function currentMonth(now = new Date()) {
  return todayInput(now).slice(0, 7)
}
