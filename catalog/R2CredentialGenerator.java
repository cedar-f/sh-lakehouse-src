package lakehouse;

import io.unitycatalog.server.service.credential.CredentialContext;
import io.unitycatalog.server.service.credential.aws.AwsCredentialGenerator;
import software.amazon.awssdk.services.sts.model.Credentials;
import com.fasterxml.jackson.databind.ObjectMapper;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;

/** R2's documented local JWT signing, scoped to the location requested by UC. */
public final class R2CredentialGenerator implements AwsCredentialGenerator {
  private static final ObjectMapper JSON = new ObjectMapper();
  private static final Base64.Encoder URL64 = Base64.getUrlEncoder().withoutPadding();
  private static String env(String key) {
    String value = System.getenv(key);
    if (value == null || value.isBlank()) throw new IllegalStateException("Missing " + key);
    return value;
  }
  private static String b64(byte[] bytes) { return URL64.encodeToString(bytes); }
  @Override public Credentials generate(CredentialContext ctx) {
    try {
      String bucket = env("R2_BUCKET");
      List<String> prefixes = new ArrayList<>();
      List<String> objects = new ArrayList<>();
      for (var location : ctx.getLocations()) {
        URI uri = location.toUri();
        if (!bucket.equals(uri.getHost())) throw new SecurityException("Unexpected bucket");
        String path = uri.getPath().replaceFirst("^/", "");
        if (path.isBlank()) throw new SecurityException("Bucket-wide vending is forbidden");
        objects.add(path.replaceFirst("/$", ""));
        prefixes.add(path.endsWith("/") ? path : path + "/");
      }
      long now = Instant.now().getEpochSecond();
      Map<String,Object> claims = new LinkedHashMap<>();
      claims.put("bucket", bucket);
      claims.put("scope", ctx.getPrivileges().contains(CredentialContext.Privilege.UPDATE)
          ? "object-read-write" : "object-read-only");
      claims.put("paths", Map.of("prefixPaths", prefixes, "objectPaths", objects));
      claims.put("sub", env("R2_ACCOUNT_ID"));
      claims.put("iss", env("R2_ACCESS_KEY_ID"));
      claims.put("aud", URI.create(env("S3_ENDPOINT")).getHost());
      claims.put("iat", now);
      claims.put("exp", now + 3600);
      String body = b64(JSON.writeValueAsBytes(Map.of("alg", "HS256", "typ", "JWT")))
          + "." + b64(JSON.writeValueAsBytes(claims));
      Mac hmac = Mac.getInstance("HmacSHA256");
      hmac.init(new SecretKeySpec(env("R2_SECRET_ACCESS_KEY").getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
      String jwt = body + "." + b64(hmac.doFinal(body.getBytes(StandardCharsets.UTF_8)));
      String secret = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256")
          .digest(jwt.getBytes(StandardCharsets.UTF_8)));
      return Credentials.builder().accessKeyId(env("R2_ACCESS_KEY_ID"))
          .secretAccessKey(secret)
          .sessionToken(Base64.getEncoder().encodeToString(("jwt/" + jwt).getBytes(StandardCharsets.UTF_8)))
          .expiration(Instant.ofEpochSecond(now + 3600)).build();
    } catch (RuntimeException ex) { throw ex; }
      catch (Exception ex) { throw new IllegalStateException("R2 credential signing failed", ex); }
  }
}
