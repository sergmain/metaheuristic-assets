public class Main {
  void main(String[] args) {
    Counter counter = new Counter();
    for (String arg : args) {
      System.out.println(counter.next() + ": " + Greeting.of(arg));
    }
  }
}
