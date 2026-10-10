package edu.abu.coursetracker.service;

import edu.abu.coursetracker.dto.CourseRequest;
import edu.abu.coursetracker.dto.CourseResponse;
import edu.abu.coursetracker.exception.ConflictException;
import edu.abu.coursetracker.exception.ResourceNotFoundException;
import edu.abu.coursetracker.model.Course;
import edu.abu.coursetracker.repository.CourseRepository;
import java.util.List;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CourseService {

    private final CourseRepository repository;

    public CourseService(CourseRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public CourseResponse create(CourseRequest request) {
        if (repository.existsByCode(request.code())) {
            throw codeInUse(request.code());
        }
        Course course = new Course();
        apply(course, request);
        return save(course);
    }

    @Transactional(readOnly = true)
    public List<CourseResponse> findAll() {
        return repository.findAll(Sort.by("id")).stream().map(CourseResponse::from).toList();
    }

    @Transactional(readOnly = true)
    public CourseResponse get(Long id) {
        return CourseResponse.from(find(id));
    }

    @Transactional
    public CourseResponse update(Long id, CourseRequest request) {
        Course course = find(id);
        if (repository.existsByCodeAndIdNot(request.code(), id)) {
            throw codeInUse(request.code());
        }
        apply(course, request);
        return save(course);
    }

    @Transactional
    public void delete(Long id) {
        repository.delete(find(id));
    }

    private Course find(Long id) {
        return repository.findById(id).orElseThrow(() -> new ResourceNotFoundException("Course", id));
    }

    private CourseResponse save(Course course) {
        try {
            return CourseResponse.from(repository.saveAndFlush(course));
        } catch (DataIntegrityViolationException e) {
            // Lost a race against a concurrent request using the same course code.
            throw codeInUse(course.getCode());
        }
    }

    private static void apply(Course course, CourseRequest request) {
        course.setCode(request.code());
        course.setName(request.name());
        course.setType(request.type());
        course.setWeeklyHours(request.weeklyHours());
        course.setGradingScheme(request.gradingScheme());
    }

    private static ConflictException codeInUse(String code) {
        return new ConflictException("Course code " + code + " is already in use");
    }
}
