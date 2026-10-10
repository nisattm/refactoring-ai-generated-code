package edu.abu.coursetracker;

import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.is;
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.emptyString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;

@SpringBootTest
@AutoConfigureMockMvc
class ApiTest {

    private static final AtomicInteger SEQ = new AtomicInteger(100000000);

    @Autowired
    MockMvc mvc;

    private ResultActions send(org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder req, String body)
            throws Exception {
        return mvc.perform(req.contentType(MediaType.APPLICATION_JSON).content(body.getBytes(StandardCharsets.UTF_8)));
    }

    private static String student(String number) {
        return """
                {"studentNumber":"%s","firstName":"Ayşe","lastName":"Yılmaz","email":"ayse@example.com"}"""
                .formatted(number);
    }

    private static String course(String code) {
        return """
                {"code":"%s","name":"Engineering Design II","type":"THEORETICAL","weeklyHours":3,"gradingScheme":"MIDTERM_PROJECT_FINAL"}"""
                .formatted(code);
    }

    private static String nextNumber() {
        return String.valueOf(SEQ.incrementAndGet());
    }

    private void assertError(ResultActions r, int status, String reason) throws Exception {
        r.andExpect(status().is(status))
                .andExpect(jsonPath("$.status", is(status)))
                .andExpect(jsonPath("$.error", is(reason)))
                .andExpect(jsonPath("$.message", not(emptyString())));
    }

    @Test
    void studentCrudLifecycle() throws Exception {
        String number = nextNumber();
        String body = student(number).replace("}", ",\"id\":999,\"extra\":true}");
        String location = send(post("/api/students"), body)
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id", not(999)))
                .andExpect(jsonPath("$.firstName", is("Ayşe")))
                .andExpect(jsonPath("$.lastName", is("Yılmaz")))
                .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        int id = com.jayway.jsonpath.JsonPath.read(location, "$.id");

        mvc.perform(get("/api/students/" + id)).andExpect(status().isOk())
                .andExpect(jsonPath("$.studentNumber", is(number)));

        String updated = student(number).replace("Ayşe", "Zeynep");
        send(put("/api/students/" + id), updated).andExpect(status().isOk())
                .andExpect(jsonPath("$.firstName", is("Zeynep")))
                .andExpect(jsonPath("$.id", is(id)));

        mvc.perform(delete("/api/students/" + id)).andExpect(status().isNoContent()).andExpect(content().string(""));
        assertError(mvc.perform(get("/api/students/" + id)), 404, "Not Found");
        assertError(mvc.perform(delete("/api/students/" + id)), 404, "Not Found");
    }

    @Test
    void studentListIsSortedById() throws Exception {
        send(post("/api/students"), student(nextNumber())).andExpect(status().isCreated());
        send(post("/api/students"), student(nextNumber())).andExpect(status().isCreated());
        String json = mvc.perform(get("/api/students")).andExpect(status().isOk()).andReturn().getResponse().getContentAsString();
        java.util.List<Integer> ids = com.jayway.jsonpath.JsonPath.read(json, "$[*].id");
        org.junit.jupiter.api.Assertions.assertEquals(ids.stream().sorted().toList(), ids);
    }

    @Test
    void studentValidation() throws Exception {
        String n = nextNumber();
        String[] bad = {
                student("12345678"),
                student("1234567890"),
                student("12345678a"),
                student("١٢٣٤٥٦٧٨٩"),
                student(n).replace("\"firstName\":\"Ayşe\",", ""),
                student(n).replace("Ayşe", "   "),
                student(n).replace("Ayşe", "x".repeat(51)),
                student(n).replace("Yılmaz", "x".repeat(51)),
                student(n).replace("ayse@example.com", "not-an-email"),
                student(n).replace("ayse@example.com", ""),
                student(n).replace("\"Ayşe\"", "123"),
                student(n).replace("\"studentNumber\":\"" + n + "\"", "\"studentNumber\":123456789"),
                "{not json",
                "[]",
                "",
        };
        for (String b : bad) {
            assertError(send(post("/api/students"), b), 400, "Bad Request");
        }
        send(post("/api/students"), student(n).replace("Ayşe", "x".repeat(50))).andExpect(status().isCreated());
    }

    @Test
    void studentConflicts() throws Exception {
        String a = nextNumber();
        String b = nextNumber();
        send(post("/api/students"), student(a)).andExpect(status().isCreated());
        assertError(send(post("/api/students"), student(a)), 409, "Conflict");
        String json = send(post("/api/students"), student(b)).andReturn().getResponse().getContentAsString();
        int id = com.jayway.jsonpath.JsonPath.read(json, "$.id");
        assertError(send(put("/api/students/" + id), student(a)), 409, "Conflict");
        send(put("/api/students/" + id), student(b)).andExpect(status().isOk());
    }

    @Test
    void pathHandling() throws Exception {
        assertError(mvc.perform(get("/api/students/abc")), 400, "Bad Request");
        assertError(mvc.perform(delete("/api/courses/abc")), 400, "Bad Request");
        assertError(send(put("/api/students/abc"), student(nextNumber())), 400, "Bad Request");
        // 404 wins over an invalid or malformed body
        assertError(send(put("/api/students/987654"), "{}"), 404, "Not Found");
        assertError(send(put("/api/students/987654"), "{broken"), 404, "Not Found");
        assertError(mvc.perform(put("/api/students/987654")), 404, "Not Found");
        assertError(send(put("/api/courses/987654"), "{}"), 404, "Not Found");
    }

    @Test
    void putValidatesExistingResource() throws Exception {
        String json = send(post("/api/students"), student(nextNumber())).andReturn().getResponse().getContentAsString();
        int id = com.jayway.jsonpath.JsonPath.read(json, "$.id");
        assertError(send(put("/api/students/" + id), "{}"), 400, "Bad Request");
        assertError(send(put("/api/students/" + id), "{broken"), 400, "Bad Request");
        assertError(send(put("/api/students/" + id), student("1").replace("\"1\"", "\"12\"")), 400, "Bad Request");
        assertError(send(put("/api/students/" + id), student(nextNumber()).replace("\"Ayşe\"", "7")), 400, "Bad Request");
    }

    @Test
    void courseCrudLifecycle() throws Exception {
        String json = send(post("/api/courses"), course("SE402").replace("}", ",\"id\":77}"))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.type", is("THEORETICAL")))
                .andExpect(jsonPath("$.weeklyHours", is(3)))
                .andExpect(jsonPath("$.gradingScheme", is("MIDTERM_PROJECT_FINAL")))
                .andReturn().getResponse().getContentAsString();
        int id = com.jayway.jsonpath.JsonPath.read(json, "$.id");
        org.junit.jupiter.api.Assertions.assertNotEquals(77, id);

        assertError(send(post("/api/courses"), course("SE402")), 409, "Conflict");
        mvc.perform(get("/api/courses/" + id)).andExpect(status().isOk()).andExpect(jsonPath("$.code", is("SE402")));
        send(put("/api/courses/" + id), course("SE402").replace("THEORETICAL", "PRACTICAL").replace(":3", ":10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.type", is("PRACTICAL")))
                .andExpect(jsonPath("$.weeklyHours", is(10)));

        String other = send(post("/api/courses"), course("CE101")).andReturn().getResponse().getContentAsString();
        int otherId = com.jayway.jsonpath.JsonPath.read(other, "$.id");
        assertError(send(put("/api/courses/" + otherId), course("SE402")), 409, "Conflict");
        send(put("/api/courses/" + otherId), course("CE101")).andExpect(status().isOk());

        mvc.perform(delete("/api/courses/" + id)).andExpect(status().isNoContent());
        assertError(mvc.perform(get("/api/courses/" + id)), 404, "Not Found");
        mvc.perform(get("/api/courses")).andExpect(status().isOk()).andExpect(jsonPath("$", hasSize(1)));
    }

    @Test
    void courseValidation() throws Exception {
        String[] bad = {
                course("A"),
                course("ABCDEFGHIJK"),
                course("se402"),
                course("SE-402"),
                course("SE 402"),
                course("İS101"),
                course("SE402").replace("\"code\":\"SE402\",", ""),
                course("SE402").replace("Engineering Design II", " "),
                course("SE402").replace("Engineering Design II", "x".repeat(101)),
                course("SE402").replace("THEORETICAL", "OTHER"),
                course("SE402").replace("THEORETICAL", "theoretical"),
                course("SE402").replace("\"type\":\"THEORETICAL\",", ""),
                course("SE402").replace("\"type\":\"THEORETICAL\"", "\"type\":null"),
                course("SE402").replace(":3", ":0"),
                course("SE402").replace(":3", ":11"),
                course("SE402").replace(":3", ":3.5"),
                course("SE402").replace(":3", ":\"3\""),
                course("SE402").replace(":3", ":99999999999999"),
                course("SE402").replace(":3", ":null"),
                course("SE402").replace("MIDTERM_PROJECT_FINAL", "FINAL_ONLY"),
                course("SE402").replace("\"code\":\"SE402\"", "\"code\":42"),
                "{bad",
        };
        for (String b : bad) {
            assertError(send(post("/api/courses"), b), 400, "Bad Request");
        }
        send(post("/api/courses"), course("S2")).andExpect(status().isCreated());
        send(post("/api/courses"), course("ABCDE12345").replace(":3", ":1")).andExpect(status().isCreated());
    }

    @Test
    void unknownPathUsesErrorFormat() throws Exception {
        assertError(mvc.perform(get("/api/nothing")), 404, "Not Found");
    }
}
