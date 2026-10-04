public class Greeting {
  static String of(String name) {
    if (name == null || name.isBlank()) {
      return "Hello, NRVV";
    }
    return "Hello, " + name.strip();
  }
}
