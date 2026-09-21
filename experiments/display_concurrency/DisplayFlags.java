import java.lang.reflect.*;
public final class DisplayFlags {
 public static void main(String[] args) throws Exception {
  Class<?> manager=Class.forName("android.hardware.display.DisplayManagerGlobal");
  Object instance=manager.getMethod("getInstance").invoke(null);
  int id=Integer.parseInt(args[0]);
  Object info=manager.getMethod("getDisplayInfo", int.class).invoke(instance,id);
  if(info==null) throw new IllegalStateException("Display absent");
  int flags=info.getClass().getField("flags").getInt(info);
  System.out.println("{\"display_id\":"+id+",\"flags\":"+flags+"}");
 }
}