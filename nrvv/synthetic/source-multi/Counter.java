public class Counter {
  private int count;

  int next() {
    if (count == Integer.MAX_VALUE) {
      throw new IllegalStateException("counter overflow");
    }
    return ++count;
  }

  void reset() {
    count = 0;
  }
}
